# =============================================================================
# 平台示範頁用的評分輸出（website/platform/）
#   資料：Python 跨球館模擬器 volley-sim/platform（4 館、150 人、8 週，跨館 10%）
#   模型：fit_platform_model()（階層模型，自報當先驗、主場球館為隨機效果）
#   另跑 online_run()：每打完一局就更新，記錄每位球員的實力與區間如何隨局數收斂
# 輸出：
#   output/ratings_platform_sim.csv   每人 theta、se、95% 區間（模型尺度，全體平均 = 0）
#   output/venues_platform_sim.csv    各館平均實力 alpha
#   output/online_trace_platform_sim.csv  每人每局後的 mu、sd
#   output/platform_sim_scale.json    模型尺度 <-> 模擬真值尺度的換算（只有模擬才有真值）
# =============================================================================
source("R/rating_model.R"); source("R/platform_model.R"); source("R/read_platform_sim.R")
DIR <- Sys.getenv("PLAT_DIR", "../volley-sim/platform")
ps <- read_platform_sim(DIR)
info <- ps$players[, c("player", "home_venue", "level")]
fit <- fit_platform_model(ps$games, info, use_venue = TRUE)
print(fit)

al <- setNames(fit$venues$alpha, fit$venues$venue)
st <- online_init(info, fit$sigma, beta = fit$beta[[1]], alpha = al)
games <- ps$games; games$night <- paste(games$date, games$session)
st <- online_run(st, games, delta = fit$delta, trace_players = info$player)
tr <- attr(st, "trace")
tr$sd <- sqrt(tr$v); tr$v <- NULL

# 尺度換算：模擬真值 -> 模型尺度（線性迴歸斜率 k，與 06_platform_python.R 相同作法）
m <- merge(fit$ratings, ps$truth$players)
k <- unname(coef(lm(theta ~ theta_true, data = m))[2])
scale <- list(k = k, theta_true_mean = mean(m$theta_true), sigma = fit$sigma, sigma_v = fit$sigma_v,
              beta = unname(fit$beta[[1]]), delta = unname(fit$delta),
              spearman_model_truth = cor(m$theta, m$theta_true, method = "spearman"),
              spearman_self_truth = cor(m$level, m$theta_true, method = "spearman"),
              coverage = mean(m$lower < k * (m$theta_true - mean(m$theta_true)) &
                              k * (m$theta_true - mean(m$theta_true)) < m$upper),
              online_batch_cor = cor(st[fit$ratings$player, "mu"], fit$ratings$theta),
              n_games = nrow(ps$games), n_players = nrow(fit$ratings))
dir.create("output", showWarnings = FALSE)
write.csv(fit$ratings, "output/ratings_platform_sim.csv", row.names = FALSE)
write.csv(fit$venues, "output/venues_platform_sim.csv", row.names = FALSE)
write.csv(tr, "output/online_trace_platform_sim.csv", row.names = FALSE)
writeLines(paste0("{", paste(sprintf('"%s": %.6g', names(scale), unlist(scale)), collapse = ", "), "}"),
           "output/platform_sim_scale.json")
str(scale)
