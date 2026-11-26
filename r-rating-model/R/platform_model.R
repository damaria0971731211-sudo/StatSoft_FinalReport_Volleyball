# =============================================================================
# 跨球館平台版：球館隨機效果的階層 Bradley-Terry ＋ 貝氏線上更新
#
# 需先 source("R/rating_model.R")（沿用 build_design 等工具）
#
# 批次模型（fit_platform_model）
#   logit P(A 隊得一分) = mean(theta[A]) - mean(theta[B]) + delta * (n_A - n_B)
#   theta_i ~ N(alpha[h(i)] + beta[k(i)] * (自報_i - 3), sigma^2)
#   alpha_v ~ N(0, sigma_v^2)            主場球館的平均實力（隨機效果）
#   beta_k  ~ N(0, 10^2)                 自報每升一級的實力；可設定各館各自一套分級（level_by_venue）
#   同一局兩隊一定在同一個球館，所以球館本身不進比賽式；球館只透過「誰的主場在哪」
#   影響先驗。跨館比較能成立，靠的是到多個球館打球的「橋接球員」。
#
# 參數向量 u = (beta[1:k], delta, alpha[1:V], theta[1:p])
# 先驗精確度 Q = M'M / sigma^2 + diag(固定效果與 alpha 的先驗精確度)
#   其中 M = [-L, 0, -A, I]，L 為自報設計、A 為主場指標矩陣
# =============================================================================

build_platform_design <- function(games, players, level_by_venue = FALSE) {
  d <- build_design(games, players)
  p <- length(d$ids)
  home <- players$home_venue[match(d$ids, players$player)]
  if (any(is.na(home))) {
    # 沒填主場的人：以出賽最多的球館當主場
    ra <- split_roster(games$team_a); rb <- split_roster(games$team_b)
    long <- data.frame(player = c(unlist(ra), unlist(rb)),
                       venue = c(rep(games$venue, lengths(ra)), rep(games$venue, lengths(rb))))
    mode_v <- tapply(long$venue, long$player, function(v) names(which.max(table(v))))
    home[is.na(home)] <- mode_v[d$ids[is.na(home)]]
  }
  venues <- sort(unique(c(home, games$venue)))
  A <- sparseMatrix(i = seq_len(p), j = match(home, venues), x = 1, dims = c(p, length(venues)))
  if (level_by_venue) {
    Lm <- sparseMatrix(i = seq_len(p), j = match(home, venues), x = d$lc, dims = c(p, length(venues)))
  } else {
    Lm <- Matrix(d$lc, ncol = 1, sparse = TRUE)
  }
  # 每位球員去過幾個球館
  ra <- split_roster(games$team_a); rb <- split_roster(games$team_b)
  long <- unique(data.frame(player = c(unlist(ra), unlist(rb)),
                            venue = c(rep(games$venue, lengths(ra)), rep(games$venue, lengths(rb)))))
  n_venues <- as.integer(table(factor(long$player, levels = d$ids)))
  c(d, list(A = A, Lm = Lm, home = home, venues = venues, n_venues_played = n_venues))
}

fit_platform_map <- function(d, sigma, sigma_v, use_venue = TRUE, use_size = TRUE,
                             start = NULL, tol = 1e-8, maxit = 50) {
  p <- ncol(d$X); k <- ncol(d$Lm); V <- ncol(d$A); n <- nrow(d$X)
  sz <- if (use_size) d$size_diff else rep(0, n)
  D <- cbind(Matrix(0, n, k, sparse = TRUE), sz, Matrix(0, n, V, sparse = TRUE), d$X)
  D <- as(D, "CsparseMatrix")
  M <- cbind(-d$Lm, Matrix(0, p, 1, sparse = TRUE), if (use_venue) -d$A else Matrix(0, p, V, sparse = TRUE),
             Diagonal(p))
  fixed_prec <- c(rep(1 / 100, k), 1, rep(if (use_venue) 1 / sigma_v^2 else 1, V), rep(0, p))
  Q <- forceSymmetric(crossprod(M) / sigma^2 + Diagonal(x = fixed_prec))
  Q <- as(Q, "CsparseMatrix")
  N <- d$a + d$b
  u <- if (is.null(start) || length(start) != ncol(D)) rep(0, ncol(D)) else start
  for (it in seq_len(maxit)) {
    eta <- as.numeric(D %*% u); mu <- plogis(eta); w <- N * mu * (1 - mu)
    grad <- as.numeric(crossprod(D, d$a - N * mu)) - as.numeric(Q %*% u)
    H <- forceSymmetric(crossprod(D, Diagonal(x = w) %*% D) + Q)
    step <- as.numeric(solve(H, grad)); u <- u + step
    if (max(abs(step)) < tol) break
  }
  eta <- as.numeric(D %*% u); mu <- plogis(eta); w <- N * mu * (1 - mu)
  H <- forceSymmetric(crossprod(D, Diagonal(x = w) %*% D) + Q)
  loglik <- sum(d$a * eta - N * log1p(exp(eta)))
  lml <- loglik - 0.5 * sum(u * as.numeric(Q %*% u)) +
    0.5 * as.numeric(determinant(Q, logarithm = TRUE)$modulus) -
    0.5 * as.numeric(determinant(H, logarithm = TRUE)$modulus)
  list(u = u, H = H, lml = lml, p = p, k = k, V = V)
}

fit_platform_model <- function(games, players, use_venue = TRUE, level_by_venue = FALSE,
                               use_size = NULL, sigma = NULL, sigma_v = NULL, level = 0.95) {
  d <- build_platform_design(games, players, level_by_venue)
  if (is.null(use_size)) use_size <- any(d$size_diff != 0)
  start <- NULL
  obj <- function(lp) {
    f <- fit_platform_map(d, exp(lp[1]), if (use_venue) exp(lp[2]) else 1, use_venue, use_size, start = start)
    start <<- f$u; -f$lml
  }
  if (is.null(sigma)) {
    if (use_venue) {
      opt <- optim(log(c(0.4, 0.3)), obj, method = "L-BFGS-B",
                   lower = log(c(0.02, 0.01)), upper = log(c(5, 5)))
      sigma <- exp(opt$par[1]); sigma_v <- exp(opt$par[2])
    } else {
      sigma <- exp(optimize(obj, log(c(0.02, 5)))$minimum); sigma_v <- NA
    }
  }
  f <- fit_platform_map(d, sigma, if (use_venue) sigma_v else 1, use_venue, use_size, start = start)
  Vc <- solve(f$H); se <- sqrt(pmax(diag(Vc), 0)); z <- qnorm(1 - (1 - level) / 2)
  k <- f$k; V <- f$V; p <- f$p
  i_beta <- seq_len(k); i_delta <- k + 1; i_alpha <- k + 1 + seq_len(V); i_theta <- k + 1 + V + seq_len(p)
  # 以全體平均為 0 呈現
  C <- Diagonal(p) - Matrix(1 / p, p, p)
  th <- as.numeric(C %*% f$u[i_theta])
  se_t <- sqrt(pmax(diag(as.matrix(C %*% Vc[i_theta, i_theta] %*% t(C))), 0))
  ratings <- data.frame(player = d$ids, theta = th, se = se_t,
                        lower = th - z * se_t, upper = th + z * se_t,
                        level = d$level, home_venue = d$home,
                        sets = as.integer(colSums(d$X != 0)), n_venues = d$n_venues_played)
  ratings <- ratings[order(-ratings$theta), ]
  # 球館平均：以 alpha 呈現（相對各館平均）
  Cv <- Diagonal(V) - Matrix(1 / V, V, V)
  al <- as.numeric(Cv %*% f$u[i_alpha])
  se_a <- sqrt(pmax(diag(as.matrix(Cv %*% Vc[i_alpha, i_alpha] %*% t(Cv))), 0))
  venues <- data.frame(venue = d$venues, alpha = al, se = se_a, lower = al - z * se_a, upper = al + z * se_a,
                       n_home = as.integer(colSums(d$A)))
  structure(list(ratings = ratings, venues = venues,
                 beta = setNames(f$u[i_beta], if (k > 1) d$venues else "全體"), beta_se = se[i_beta],
                 delta = f$u[i_delta], delta_se = se[i_delta],
                 sigma = sigma, sigma_v = sigma_v, lml = f$lml, design = d, use_size = use_size,
                 use_venue = use_venue, level_by_venue = level_by_venue),
            class = "platform_fit")
}

print.platform_fit <- function(x, ...) {
  cat("跨球館實力評分模型\n")
  cat(sprintf("  球員 %d 人、球館 %d 間、局數 %d\n", nrow(x$ratings), nrow(x$venues), nrow(x$design$X)))
  cat(sprintf("  sigma（個人）= %.3f   sigma_v（球館平均）= %s\n", x$sigma,
              if (is.na(x$sigma_v)) "未納入" else sprintf("%.3f", x$sigma_v)))
  cat("  beta（自報每升一級）：", paste(sprintf("%s %.2f", names(x$beta), x$beta), collapse = "，"), "\n")
  cat(sprintf("  跨館球員（去過 ≥2 館）：%d 人\n", sum(x$ratings$n_venues >= 2)))
  invisible(x)
}

# =============================================================================
# 貝氏線上更新（每打完一局就更新，平台即時用）
#   每位球員只存 (mu, v)：實力的後驗平均與變異數。新人以先驗初始化：
#     mu = alpha[主場] + beta * (自報 - 3)，v = sigma^2
#   打完一局（A 得 a 分、B 得 b 分，共 N 球）：
#     eta = sum_A w_j mu_j - sum_B w_j mu_j + delta (n_A - n_B)，w_j = 1/隊伍人數
#     s2  = sum w_j^2 v_j       （隊伍強度本身的不確定性）
#     kappa = 1 / sqrt(1 + pi * s2 / 8)，p = plogis(kappa * eta)  （對不確定性做機率修正）
#     對每位場上球員 j（B 隊符號相反）：
#       資訊量 I_j = w_j^2 kappa^2 N p (1-p)
#       v_j <- 1 / (1/v_j + I_j)
#       mu_j <- mu_j + v_j * (± w_j kappa (a - N p))
#   這是 Laplace 近似的「假設密度濾波」（assumed density filtering），與 Glicko 同一家族。
#   drift：每晚開始前 v_j 加上 drift^2，讓實力可以隨時間慢慢變（進步）。
# =============================================================================
online_init <- function(players, sigma, beta = 0.4, alpha = NULL) {
  a0 <- if (is.null(alpha) || is.null(players$home_venue)) 0 else {
    x <- alpha[players$home_venue]; x[is.na(x)] <- 0; x }
  lc <- players$level - 3; lc[is.na(lc)] <- 0
  st <- data.frame(player = players$player, mu = a0 + beta * lc, v = sigma^2, sets = 0L)
  rownames(st) <- st$player
  st
}

online_update <- function(state, team_a, team_b, score_a, score_b, delta = 0) {
  ia <- match(team_a, state$player); ib <- match(team_b, state$player)
  wa <- 1 / length(ia); wb <- 1 / length(ib)
  eta <- wa * sum(state$mu[ia]) - wb * sum(state$mu[ib]) + delta * (length(ia) - length(ib))
  s2 <- wa^2 * sum(state$v[ia]) + wb^2 * sum(state$v[ib])
  kappa <- 1 / sqrt(1 + pi * s2 / 8)
  N <- score_a + score_b; p <- plogis(kappa * eta)
  resid <- score_a - N * p; info <- kappa^2 * N * p * (1 - p)
  for (k in list(list(i = ia, w = wa, sgn = 1), list(i = ib, w = wb, sgn = -1))) {
    v_new <- 1 / (1 / state$v[k$i] + k$w^2 * info)
    state$mu[k$i] <- state$mu[k$i] + v_new * k$sgn * k$w * kappa * resid
    state$v[k$i] <- v_new
    state$sets[k$i] <- state$sets[k$i] + 1L
  }
  state
}

online_run <- function(state, games, delta = 0, drift = 0, trace_players = NULL) {
  tr <- list(); night_prev <- NULL
  for (g in seq_len(nrow(games))) {
    nk <- if (!is.null(games$night)) paste(games$venue[g], games$night[g]) else NULL
    if (drift > 0 && !is.null(nk) && !identical(nk, night_prev)) state$v <- state$v + drift^2
    night_prev <- nk
    ta <- strsplit(games$team_a[g], ";", fixed = TRUE)[[1]]
    tb <- strsplit(games$team_b[g], ";", fixed = TRUE)[[1]]
    state <- online_update(state, ta, tb, games$score_a[g], games$score_b[g], delta)
    if (!is.null(trace_players)) {
      hit <- intersect(c(ta, tb), trace_players)
      if (length(hit)) tr[[length(tr) + 1]] <- state[hit, c("player", "mu", "v", "sets")]
    }
  }
  attr(state, "trace") <- if (length(tr)) do.call(rbind, tr) else NULL
  state
}
