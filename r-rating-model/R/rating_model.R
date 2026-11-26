# =============================================================================
# 野場排球球員實力評分模型（Bayesian rally-level Bradley-Terry + 搭檔收縮）
#
# 資料格式（每列一局）：
#   date, session, game_id, team_a, team_b, score_a, score_b
#   team_a / team_b 為以 ";" 分隔的球員代號，例如 "P01;P07;P12;P20;P33"
# 球員表（選用）：player, level  （自報程度 1–5，可缺）
#
# 模型：
#   每一球（rally）A 隊得分機率 p，logit(p) = eta
#   eta = mean(theta[A]) - mean(theta[B]) + mean(gamma[A 隊內搭檔]) - mean(gamma[B 隊內搭檔])
#         + delta * (n_A - n_B)                    人數差效果（野場常有 4 打 5）
#   score_a | eta  ~ 似然核 p^score_a (1-p)^score_b   （見下方註解，與停止規則無關）
#   theta_i ~ N(beta * (level_i - 3), sigma^2)   自報程度作為先驗平均
#   gamma_jk ~ N(0, tau^2)                        搭檔默契，向 0 收縮
#   beta ~ N(0, 10^2)
#   超參數 (sigma, tau) 以 Laplace 近似的邊際概似最大化估計（經驗貝氏）
#   後驗以 Laplace 近似：MAP ± 1.96 * sqrt(diag(H^-1))
#
# 為何可以用二項似然：若每球獨立且 A 得分機率皆為 p，一局打到 25 分（deuce 須贏 2 分）
# 的停止規則只與比分有關、與 p 無關，因此該局比分序列的機率 = 常數 × p^a (1-p)^b，
# 對 p 的似然與二項分佈完全相同（likelihood principle）。
#
# 只依賴 base R + stats；Matrix 用於稀疏矩陣加速。
# =============================================================================

suppressPackageStartupMessages(library(Matrix))

split_roster <- function(x) strsplit(as.character(x), ";", fixed = TRUE)

pair_key <- function(a, b) ifelse(a < b, paste(a, b, sep = "|"), paste(b, a, sep = "|"))

team_pairs <- function(roster) {
  if (length(roster) < 2) return(character(0))
  cmb <- utils::combn(sort(roster), 2)
  paste(cmb[1, ], cmb[2, ], sep = "|")
}

# 由比賽紀錄建立設計矩陣 -------------------------------------------------------
build_design <- function(games, players = NULL, min_pair_sets = 1) {
  ra <- split_roster(games$team_a)
  rb <- split_roster(games$team_b)
  ids <- sort(unique(c(unlist(ra), unlist(rb), if (!is.null(players)) players$player)))
  n <- nrow(games); p <- length(ids)

  # 球員矩陣 X：A 隊 +1/n_A，B 隊 -1/n_B
  ii <- integer(0); jj <- integer(0); xx <- numeric(0)
  for (g in seq_len(n)) {
    a <- match(ra[[g]], ids); b <- match(rb[[g]], ids)
    ii <- c(ii, rep(g, length(a) + length(b)))
    jj <- c(jj, a, b)
    xx <- c(xx, rep(1 / length(a), length(a)), rep(-1 / length(b), length(b)))
  }
  X <- sparseMatrix(i = ii, j = jj, x = xx, dims = c(n, p), dimnames = list(NULL, ids))

  # 搭檔矩陣 Z：只納入至少同隊 min_pair_sets 局的搭檔
  pa <- lapply(ra, team_pairs); pb <- lapply(rb, team_pairs)
  cnt <- table(c(unlist(pa), unlist(pb)))
  pairs <- sort(names(cnt)[cnt >= min_pair_sets])
  ii <- integer(0); jj <- integer(0); xx <- numeric(0)
  for (g in seq_len(n)) {
    a <- match(pa[[g]], pairs); b <- match(pb[[g]], pairs)
    na <- length(pa[[g]]); nb <- length(pb[[g]])
    a <- a[!is.na(a)]; b <- b[!is.na(b)]
    ii <- c(ii, rep(g, length(a) + length(b)))
    jj <- c(jj, a, b)
    xx <- c(xx, rep(1 / na, length(a)), rep(-1 / nb, length(b)))
  }
  Z <- sparseMatrix(i = ii, j = jj, x = xx, dims = c(n, length(pairs)),
                    dimnames = list(NULL, pairs))

  level <- rep(NA_real_, p)
  if (!is.null(players) && "level" %in% names(players)) {
    level <- players$level[match(ids, players$player)]
  }
  lc <- level - 3
  lc[is.na(lc)] <- 0          # 未自報者先驗平均 = 全體平均
  size_diff <- lengths(ra) - lengths(rb)
  list(X = X, Z = Z, size_diff = size_diff, ids = ids, pairs = pairs, lc = lc, level = level,
       a = games$score_a, b = games$score_b,
       pair_sets = as.integer(cnt[pairs]))
}

# 給定超參數，以 Newton (IRLS) 求 MAP ---------------------------------------
# 參數向量 u = (beta, delta, theta[1:p], gamma[1:q])
#   beta  ：自報程度每升一級對應的實力（只出現在 theta 的先驗平均）
#   delta ：人數效果，A 隊每多一人 rally logit 增加 delta（先驗 N(0, 1)）
fit_map <- function(d, sigma, tau, use_level = TRUE, use_pairs = TRUE, use_size = TRUE,
                    start = NULL, tol = 1e-8, maxit = 50) {
  p <- ncol(d$X); q <- if (use_pairs) ncol(d$Z) else 0
  n <- nrow(d$X)
  sz <- if (use_size) d$size_diff else rep(0, n)
  D <- if (use_pairs) cbind(0, sz, d$X, d$Z) else cbind(0, sz, d$X)
  D <- as(D, "CsparseMatrix")
  L <- if (use_level) d$lc else rep(0, p)
  it_ <- 3:(p + 2)
  # 先驗精確度矩陣 Q（theta_i - beta * L_i ~ N(0, sigma^2)）
  Q <- Matrix(0, p + 2 + q, p + 2 + q, sparse = TRUE)
  Q[1, 1] <- if (use_level) sum(L^2) / sigma^2 + 1 / 100 else 1
  if (use_level) { Q[1, it_] <- -L / sigma^2; Q[it_, 1] <- -L / sigma^2 }
  Q[2, 2] <- 1
  Q[cbind(it_, it_)] <- 1 / sigma^2
  if (q > 0) { ig <- (p + 3):(p + 2 + q); Q[cbind(ig, ig)] <- 1 / tau^2 }
  Q <- as(Q, "CsparseMatrix")

  N <- d$a + d$b
  u <- if (is.null(start) || length(start) != ncol(D)) rep(0, ncol(D)) else start
  for (it in seq_len(maxit)) {
    eta <- as.numeric(D %*% u)
    mu <- plogis(eta)
    w <- N * mu * (1 - mu)
    grad <- as.numeric(crossprod(D, d$a - N * mu)) - as.numeric(Q %*% u)
    H <- forceSymmetric(crossprod(D, Diagonal(x = w) %*% D) + Q)
    step <- as.numeric(solve(H, grad))
    u <- u + step
    if (max(abs(step)) < tol) break
  }
  eta <- as.numeric(D %*% u); mu <- plogis(eta); w <- N * mu * (1 - mu)
  H <- forceSymmetric(crossprod(D, Diagonal(x = w) %*% D) + Q)
  loglik <- sum(d$a * eta - N * log1p(exp(eta)))  # 二項核（省略與參數無關的常數）
  # Laplace 邊際概似：loglik - u'Qu/2 + log|Q|/2 - log|H|/2
  logdetQ <- as.numeric(determinant(Q, logarithm = TRUE)$modulus)
  logdetH <- as.numeric(determinant(H, logarithm = TRUE)$modulus)
  lml <- loglik - 0.5 * sum(u * as.numeric(Q %*% u)) + 0.5 * logdetQ - 0.5 * logdetH
  list(u = u, H = H, lml = lml, loglik = loglik, iter = it,
       p = p, q = q, use_level = use_level, use_pairs = use_pairs, use_size = use_size)
}

# 估超參數 + 輸出結果 ----------------------------------------------------------
fit_rating_model <- function(games, players = NULL, use_level = TRUE, use_pairs = TRUE,
                             use_size = NULL, min_pair_sets = 1, sigma = NULL, tau = NULL, level = 0.95) {
  d <- build_design(games, players, min_pair_sets)
  if (!use_level || all(d$lc == 0)) use_level <- FALSE
  if (is.null(use_size)) use_size <- any(d$size_diff != 0)   # 人數都一樣時無法估
  start <- NULL
  obj <- function(lp) {
    s <- exp(lp[1]); t <- if (use_pairs) exp(lp[2]) else 1
    f <- fit_map(d, s, t, use_level, use_pairs, use_size, start = start)
    start <<- f$u
    -f$lml
  }
  if (is.null(sigma) || (use_pairs && is.null(tau))) {
    init <- if (use_pairs) log(c(0.5, 0.2)) else log(0.5)
    if (use_pairs) {
      opt <- optim(init, obj, method = "L-BFGS-B",
                   lower = log(c(0.02, 0.005)), upper = log(c(5, 2)))
      sigma <- exp(opt$par[1]); tau <- exp(opt$par[2])
    } else {
      opt <- optimize(function(x) obj(x), log(c(0.02, 5)))
      sigma <- exp(opt$minimum); tau <- NA
    }
  }
  f <- fit_map(d, sigma, if (use_pairs) tau else 1, use_level, use_pairs, use_size, start = start)

  V <- solve(f$H)                       # 近似後驗共變異
  se <- sqrt(pmax(diag(V), 0))
  z <- qnorm(1 - (1 - level) / 2)
  idx_t <- 3:(f$p + 2)
  # 以「相對全體平均」呈現：theta_i - mean(theta)
  C <- diag(f$p) - matrix(1 / f$p, f$p, f$p)
  th <- as.numeric(C %*% f$u[idx_t])
  Vt <- as.matrix(V[idx_t, idx_t])
  se_t <- sqrt(pmax(diag(C %*% Vt %*% t(C)), 0))
  ratings <- data.frame(player = d$ids, theta = th, se = se_t,
                        lower = th - z * se_t, upper = th + z * se_t,
                        level = d$level,
                        sets = as.integer(colSums(d$X != 0)))
  ratings <- ratings[order(-ratings$theta), ]
  pairs <- NULL
  if (use_pairs && f$q > 0) {
    idx_g <- (f$p + 3):(f$p + 2 + f$q)
    g <- f$u[idx_g]; sg <- se[idx_g]
    pairs <- data.frame(pair = d$pairs, gamma = g, se = sg,
                        lower = g - z * sg, upper = g + z * sg, sets_together = d$pair_sets)
    pairs <- pairs[order(-pairs$gamma), ]
  }
  structure(list(ratings = ratings, pairs = pairs,
                 beta = f$u[1], beta_se = se[1], delta = f$u[2], delta_se = se[2],
                 sigma = sigma, tau = tau,
                 lml = f$lml, loglik = f$loglik, fit = f, design = d,
                 use_level = use_level, use_pairs = use_pairs, use_size = use_size),
            class = "rating_fit")
}

print.rating_fit <- function(x, ...) {
  cat("野場排球實力評分模型\n")
  cat(sprintf("  球員 %d 人、局數 %d、搭檔組合 %d\n", nrow(x$ratings), nrow(x$design$X),
              if (is.null(x$pairs)) 0 else nrow(x$pairs)))
  cat(sprintf("  sigma（個人實力離散）= %.3f   tau（搭檔效果離散）= %s\n", x$sigma,
              if (is.na(x$tau)) "未納入" else sprintf("%.3f", x$tau)))
  if (x$use_level) cat(sprintf("  beta（自報每升一級的 logit 實力）= %.3f (SE %.3f)\n", x$beta, x$beta_se))
  if (x$use_size) cat(sprintf("  delta（多一人的 logit 優勢）= %.3f (SE %.3f)\n", x$delta, x$delta_se))
  cat(sprintf("  Laplace 邊際對數概似 = %.2f\n", x$lml))
  invisible(x)
}

# 預測新的一局：回傳 A 隊每球得分機率、A 贏局機率 --------------------------------
predict_set <- function(fit, team_a, team_b, target = 20) {
  th <- setNames(fit$ratings$theta, fit$ratings$player)
  gm <- if (!is.null(fit$pairs)) setNames(fit$pairs$gamma, fit$pairs$pair) else numeric(0)
  team_strength <- function(r) {
    s <- mean(ifelse(r %in% names(th), th[r], 0))
    pr <- team_pairs(r)
    if (length(pr)) s <- s + mean(ifelse(pr %in% names(gm), gm[pr], 0))
    s
  }
  eta <- team_strength(team_a) - team_strength(team_b)
  if (isTRUE(fit$use_size)) eta <- eta + fit$delta * (length(team_a) - length(team_b))
  p <- plogis(eta)
  c(p_rally = p, p_set = set_win_prob(p, target))
}

# 每球得分機率 p 時，先到 target 分（須領先 2 分）贏下一局的機率
set_win_prob <- function(p, target = 25) {
  q <- 1 - p
  # 在 target-1 : k (k <= target-2) 時拿下最後一分
  k <- 0:(target - 2)
  win_direct <- sum(choose(target - 1 + k, k) * p^target * q^k)
  # 打到 (target-1):(target-1) 進入 deuce
  deuce <- choose(2 * target - 2, target - 1) * p^(target - 1) * q^(target - 1)
  win_direct + deuce * p^2 / (p^2 + q^2)
}
