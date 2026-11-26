# =============================================================================
# 多球館模擬（開發與驗證用；完整的多球館資料由 Python 模擬器產生）
#   每間球館有自己的平均實力 alpha_v ~ N(0, sigma_v^2)（例如有校隊常駐的球館較強）
#   球員 theta_i = alpha_{主場} + N(0, sigma^2)
#   自報程度：level_mode = "venue"  → 各館自己分級（跟同館的人比；跨館不可比，這是現實中的問題）
#             level_mode = "global" → 全台同一把尺
#   比例 p_travel 的球員是「跑館的人」，除了主場也會去別館打（橋接球員）
# =============================================================================
simulate_platform_players <- function(n_venues = 5, per_venue = 40, sigma = 0.5, sigma_v = 0.4,
                                      p_travel = 0.1, level_cor = 0.7, level_mode = c("venue", "global"),
                                      seed = NULL) {
  level_mode <- match.arg(level_mode)
  if (!is.null(seed)) set.seed(seed)
  venues <- sprintf("V%d", seq_len(n_venues))
  alpha <- rnorm(n_venues, 0, sigma_v); alpha <- alpha - mean(alpha)
  n <- n_venues * per_venue
  home <- rep(venues, each = per_venue)
  dev <- rnorm(n, 0, sigma)
  theta <- alpha[match(home, venues)] + dev
  ref <- if (level_mode == "venue") dev / sigma else theta / sqrt(sigma^2 + sigma_v^2)
  z <- ref * level_cor + sqrt(1 - level_cor^2) * rnorm(n)
  level <- pmin(5, pmax(1, round(3 + z)))
  list(players = data.frame(player = sprintf("P%03d", seq_len(n)), home_venue = home,
                            theta_true = theta, level = level,
                            traveler = runif(n) < p_travel, attend = runif(n, 0.3, 0.9)),
       venues = data.frame(venue = venues, alpha_true = alpha))
}

simulate_platform_games <- function(truth, n_nights = 16, sets_per_night = 12,
                                    foreign_weight = 0.3, targets = c(20, 15), target_prob = c(0.7, 0.3)) {
  pl <- truth$players; th <- setNames(pl$theta_true, pl$player)
  out <- list(); gid <- 0
  for (v in truth$venues$venue) for (night in seq_len(n_nights)) {
    cand <- pl$home_venue == v | pl$traveler
    w <- pl$attend * ifelse(pl$home_venue == v, 1, foreign_weight)
    n_teams <- sample(4:6, 1); size <- sample(4:6, 1)
    present <- sample(pl$player[cand], n_teams * size, prob = w[cand])
    teams <- split(sample(present), rep(seq_len(n_teams), length.out = length(present)))
    for (s in seq_len(sets_per_night)) {
      ab <- sample(seq_len(n_teams), 2); ta <- teams[[ab[1]]]; tb <- teams[[ab[2]]]
      tgt <- sample(targets, 1, prob = target_prob)
      sc <- play_set(plogis(mean(th[ta]) - mean(th[tb])), tgt)
      gid <- gid + 1
      out[[gid]] <- data.frame(venue = v, night = night, game_id = gid,
                               team_a = paste(ta, collapse = ";"), team_b = paste(tb, collapse = ";"),
                               score_a = sc[1], score_b = sc[2], target = tgt)
    }
  }
  g <- do.call(rbind, out)
  g[order(g$night, g$venue, g$game_id), ]   # 依時間順序（各館同一週並行）
}
