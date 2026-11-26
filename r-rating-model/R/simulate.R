# =============================================================================
# 野場排球模擬資料產生器（用於驗證評分模型；與 Python 端的產生器輸出同一格式）
#
# 每晚：隨機決定隊數（4–6）與每隊人數（4–6），從球員池抽出當晚出席者，
#       依 formation 分隊（random = 隨機；level = 依自報程度蛇形分隊），
#       接著打 sets_per_night 局，每局隨機挑兩隊，逐球模擬到 20 分（30% 機率是 15 分短局；須贏 2 分），
#       對應政大野場規則（晚餐 18:00–19:30、消夜 22:00–23:30，打 15 或 20 分）。
# 真實參數：theta_i ~ N(0, sigma^2)，gamma_jk ~ N(0, tau^2) 後雙重中心化（純交互作用）
# 自報程度：level = round(3 + theta / sigma * r + sqrt(1 - r^2) * e)，截在 1–5，
#           r 控制自報與真實實力的相關（預設 0.7）
# =============================================================================

simulate_players <- function(n_players = 40, sigma = 0.5, tau = 0.3, level_cor = 0.7,
                             seed = NULL) {
  if (!is.null(seed)) set.seed(seed)
  ids <- sprintf("P%02d", seq_len(n_players))
  theta <- rnorm(n_players, 0, sigma)
  z <- theta / sigma * level_cor + sqrt(1 - level_cor^2) * rnorm(n_players)
  level <- pmin(5, pmax(1, round(3 + z)))
  cmb <- utils::combn(ids, 2)
  # 搭檔效果只保留「純交互作用」：把對稱矩陣做雙重中心化（扣掉每人的平均搭檔效果），
  # 否則「某人跟誰搭都比較好」會跟個人實力 theta 混在一起、無法辨識。
  G <- matrix(0, n_players, n_players)
  G[lower.tri(G)] <- rnorm(ncol(cmb), 0, tau); G <- G + t(G)
  r <- rowSums(G) / (n_players - 2); m <- sum(G) / ((n_players - 1) * (n_players - 2))
  G <- G - outer(r, r, "+") + m; diag(G) <- 0
  pairs <- data.frame(pair = paste(cmb[1, ], cmb[2, ], sep = "|"),
                      gamma = G[cbind(match(cmb[1, ], ids), match(cmb[2, ], ids))])
  list(players = data.frame(player = ids, level = level, theta_true = theta,
                            attend = runif(n_players, 0.3, 0.9)),
       pairs = pairs, sigma = sigma, tau = tau)
}

play_set <- function(p, target = 25) {
  a <- 0L; b <- 0L
  repeat {
    if (runif(1) < p) a <- a + 1L else b <- b + 1L
    if ((a >= target || b >= target) && abs(a - b) >= 2) break
  }
  c(a, b)
}

form_teams <- function(present, levels, n_teams, formation = c("random", "level")) {
  formation <- match.arg(formation)
  if (formation == "random") {
    present <- sample(present)
  } else {
    present <- present[order(-levels[present], runif(length(present)))]
  }
  # 蛇形分配：1,2,...,K,K,...,1,...
  k <- rep(c(seq_len(n_teams), rev(seq_len(n_teams))), length.out = length(present))
  split(present, k)
}

simulate_league <- function(truth, n_nights = 16, sets_per_night = 12,
                            formation = "random", targets = c(20, 15), target_prob = c(0.7, 0.3), start_date = as.Date("2026-09-14")) {
  pl <- truth$players
  th <- setNames(pl$theta_true, pl$player)
  lv <- setNames(pl$level, pl$player)
  gm <- setNames(truth$pairs$gamma, truth$pairs$pair)
  strength <- function(r) {
    s <- mean(th[r]); pr <- team_pairs(r)
    s + mean(gm[pr])
  }
  out <- vector("list", n_nights); gid <- 0
  for (night in seq_len(n_nights)) {
    n_teams <- sample(4:6, 1); size <- sample(4:6, 1)
    need <- n_teams * size
    present <- sample(pl$player, need, prob = pl$attend)
    teams <- form_teams(present, lv, n_teams, formation)
    session <- ifelse(night %% 2 == 1, "晚餐場", "消夜場")
    rows <- vector("list", sets_per_night)
    for (s in seq_len(sets_per_night)) {
      ab <- sample(seq_len(n_teams), 2)
      ta <- teams[[ab[1]]]; tb <- teams[[ab[2]]]
      p <- plogis(strength(ta) - strength(tb))
      target <- sample(targets, 1, prob = target_prob)
      sc <- play_set(p, target)
      gid <- gid + 1
      rows[[s]] <- data.frame(date = start_date + (night - 1) %/% 2 * 3,
                              session = session, game_id = gid,
                              team_a = paste(ta, collapse = ";"),
                              team_b = paste(tb, collapse = ";"),
                              score_a = sc[1], score_b = sc[2], target = target, night = night)
    }
    out[[night]] <- do.call(rbind, rows)
  }
  do.call(rbind, out)
}
