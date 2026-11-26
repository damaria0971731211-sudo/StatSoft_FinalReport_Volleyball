# =============================================================================
# 跨球館：橋接球員要多少，各館的實力才能放在同一把尺上？
#   5 間球館 × 40 位主場球員，各館每週 1 晚、共 16 晚，每晚 12 局（15/20 分局）
#   各館「自己分級」（自報程度只跟同館的人比），球館平均實力 sigma_v = 0.4
#   跑館比例 p_travel：0、2%、5%、10%、20%
#   比較：不含球館效果（單一館的 M2 模型）vs 含球館隨機效果的階層模型
#   另做：線上更新 vs 批次模型；自報 vs 估計的 Bland-Altman
# =============================================================================
source("R/rating_model.R"); source("R/simulate.R"); source("R/platform_model.R"); source("R/simulate_platform.R")
library(parallel)
R_REPS <- as.integer(Sys.getenv("R_REPS", "100"))

scen <- rbind(data.frame(p_travel = c(0, 0.02, 0.05, 0.1, 0.2), level_mode = "venue"),
              data.frame(p_travel = 0.1, level_mode = "global"))

one <- function(s, rep) {
  set.seed(50000 + 1000 * s + rep)
  sc <- scen[s, ]
  tr <- simulate_platform_players(p_travel = sc$p_travel, level_mode = sc$level_mode)
  g <- simulate_platform_games(tr, 16)
  info <- tr$players[, c("player", "home_venue", "level")]
  fits <- list(單館模型_無球館效果 = fit_platform_model(g, info, use_venue = FALSE),
               階層模型_球館隨機效果 = fit_platform_model(g, info, use_venue = TRUE))
  rows <- lapply(names(fits), function(nm) {
    f <- fits[[nm]]
    m <- merge(f$ratings, tr$players[, c("player", "theta_true")])
    t <- m$theta_true - mean(m$theta_true)
    within <- mean(sapply(split(seq_len(nrow(m)), m$home_venue), function(ix)
      cor(m$theta[ix], t[ix], method = "spearman")))
    v <- merge(f$venues, tr$venues)
    data.frame(model = nm, spearman = cor(m$theta, t, method = "spearman"),
               spearman_within = within,
               rmse = sqrt(mean((m$theta - t)^2)),
               coverage = mean(m$lower < t & t < m$upper),
               venue_rmse = if (f$use_venue) sqrt(mean((v$alpha - v$alpha_true)^2)) else NA,
               venue_cov = if (f$use_venue) mean(v$lower < v$alpha_true & v$alpha_true < v$upper) else NA,
               sigma_v = f$sigma_v, bridges = sum(f$ratings$n_venues >= 2))
  })
  # 線上更新（單次依時間順序掃過所有局；先驗不含球館效果，因為新平台一開始也不知道）
  bf <- fits$階層模型_球館隨機效果
  st <- online_init(info, sigma = bf$sigma, beta = bf$beta[1])
  st <- online_run(st, g)
  m <- merge(st, tr$players[, c("player", "theta_true")])
  t <- m$theta_true - mean(m$theta_true); mu <- m$mu - mean(m$mu)
  bm <- bf$ratings$theta[match(m$player, bf$ratings$player)]
  rows[[3]] <- data.frame(model = "線上更新", spearman = cor(mu, t, method = "spearman"),
                          spearman_within = mean(sapply(split(seq_len(nrow(m)), tr$players$home_venue[match(m$player, tr$players$player)]),
                                                        function(ix) cor(mu[ix], t[ix], method = "spearman"))),
                          rmse = sqrt(mean((mu - t)^2)),
                          coverage = mean(abs(mu - t) < 1.96 * sqrt(m$v)),
                          venue_rmse = NA, venue_cov = NA, sigma_v = NA,
                          bridges = sum(bf$ratings$n_venues >= 2))
  rows[[3]]$cor_with_batch <- cor(mu, bm)
  out <- do.call(rbind, lapply(rows, function(r) { if (is.null(r$cor_with_batch)) r$cor_with_batch <- NA; r }))
  cbind(p_travel = sc$p_travel, level_mode = sc$level_mode, rep = rep, out)
}

jobs <- expand.grid(s = seq_len(nrow(scen)), rep = seq_len(R_REPS))
t0 <- Sys.time()
res <- mclapply(seq_len(nrow(jobs)), function(j) tryCatch(one(jobs$s[j], jobs$rep[j]),
                error = function(e) { message("fail ", j, ": ", conditionMessage(e)); NULL }),
                mc.cores = detectCores(), mc.preschedule = FALSE)
res <- do.call(rbind, res)
cat("完成", nrow(jobs), "次，耗時", format(Sys.time() - t0), "\n")

# 示範資料集（p_travel = 10%）：給 Bland-Altman 與球館估計圖用
set.seed(2026)
tr <- simulate_platform_players(p_travel = 0.1, level_mode = "venue")
g <- simulate_platform_games(tr, 16)
info <- tr$players[, c("player", "home_venue", "level")]
demo <- fit_platform_model(g, info, use_venue = TRUE)
dir.create("output", showWarnings = FALSE)
write.csv(demo$ratings, "output/ratings_platform_demo.csv", row.names = FALSE)
write.csv(demo$venues, "output/venues_platform_demo.csv", row.names = FALSE)
saveRDS(list(results = res, scen = scen, R_REPS = R_REPS,
             demo = list(ratings = demo$ratings, venues = merge(demo$venues, tr$venues),
                         beta = demo$beta, sigma = demo$sigma, sigma_v = demo$sigma_v,
                         truth = tr$players, n_games = nrow(g))),
        "results/platform_venues.rds")
agg <- aggregate(cbind(spearman, spearman_within, coverage, venue_rmse, venue_cov, cor_with_batch, bridges) ~
                   level_mode + p_travel + model, data = res, FUN = mean, na.action = na.pass)
print(agg[order(agg$level_mode, agg$p_travel), ], digits = 3)
