# =============================================================================
# 套用到 Python 跨球館模擬器（volley-sim/platform）：4 館、150 人、8 週
#   (1) 跨館比例 0% / 10% / 30%：階層模型 vs 不含球館效果
#   (2) 自報偏誤：Bland-Altman 與誤差迴歸（性別、球齡、主場）
#       為避免循環論證，這裡的實力估計「不使用」自報先驗（只用比賽結果＋球館效果）
# 0% 與 30% 的資料由 python platform_sim.py --cross 0 / 0.3 產生（種子相同）
# =============================================================================
source("R/rating_model.R"); source("R/platform_model.R"); source("R/read_platform_sim.R")
DIRS <- c("0%" = Sys.getenv("PLAT_CROSS0", "/tmp/claude-0/psim/cross0"),
          "10%" = Sys.getenv("PLAT_CROSS10", "/mnt/project-files/volley-sim/platform"),
          "30%" = Sys.getenv("PLAT_CROSS30", "/tmp/claude-0/psim/cross0.3"))

venue_means <- function(r, truth_p) {
  m <- merge(r, truth_p)
  data.frame(venue = names(tapply(m$theta, m$home_venue, mean)),
             est = as.numeric(tapply(m$theta, m$home_venue, mean)),
             true = as.numeric(tapply(m$theta_true, m$home_venue, mean)))
}
rows <- list(); vm_all <- list()
for (nm in names(DIRS)) {
  ps <- read_platform_sim(DIRS[[nm]])
  info <- ps$players[, c("player", "home_venue", "level")]
  for (mod in c("階層模型_球館隨機效果", "單館模型_無球館效果")) {
    f <- fit_platform_model(ps$games, info, use_venue = mod == "階層模型_球館隨機效果")
    m <- merge(f$ratings, ps$truth$players)
    # Python 模擬器的真實實力尺度和模型的 logit/每球尺度不同：先用線性迴歸把真值換到模型尺度
    k <- coef(lm(theta ~ theta_true, data = m))[2]
    t <- k * (m$theta_true - mean(m$theta_true))
    vm <- venue_means(f$ratings, ps$truth$players)
    vm$true <- k * vm$true
    vm$est <- vm$est - vm$est[1]; vm$true <- vm$true - vm$true[1]   # 相對 V01（政大）
    vm_all[[length(vm_all) + 1]] <- cbind(cross = nm, model = mod, vm)
    rows[[length(rows) + 1]] <- data.frame(
      cross = nm, model = mod, n_games = nrow(ps$games), bridges = sum(f$ratings$n_venues >= 2),
      spearman = cor(m$theta, t, method = "spearman"),
      coverage = mean(m$lower < t & t < m$upper),
      venue_gap_rmse = sqrt(mean((vm$est - vm$true)[-1]^2)),
      sigma = f$sigma, sigma_v = f$sigma_v, scale_k = k)
  }
}
tab <- do.call(rbind, rows); vm_all <- do.call(rbind, vm_all)

# ---- 自報偏誤分析（10% 資料）----
ps <- read_platform_sim(DIRS[["10%"]])
info_nolevel <- transform(ps$players[, c("player", "home_venue")], level = NA_real_)
f_nl <- fit_platform_model(ps$games, info_nolevel, use_venue = TRUE)
d <- merge(merge(f_nl$ratings[, c("player", "theta", "se", "sets")], ps$players), ps$truth$players)
# 把估計實力換到「級數」尺度：用全體的自報~實力校準線（level = a + b*theta）
cal <- lm(level ~ theta, data = d)
d$level_hat <- fitted(cal)
d$diff <- d$level - d$level_hat                   # 正 = 自報比實力高
d$avg <- (d$level + d$level_hat) / 2
cal_true <- lm(level ~ theta_true, data = d)
d$diff_true <- d$level - fitted(cal_true)         # 用真實實力算的同一個量（只有模擬才有）
reg_est <- lm(diff ~ gender + years + home_venue, data = d)
reg_true <- lm(diff_true ~ gender + years + home_venue, data = d)
coefs <- data.frame(term = names(coef(reg_est)),
                    est = coef(reg_est), est_se = sqrt(diag(vcov(reg_est))),
                    true_theta = coef(reg_true), true_se = sqrt(diag(vcov(reg_true))))
ba <- list(data = d, mean_diff = mean(d$diff), loa = mean(d$diff) + c(-1.96, 1.96) * sd(d$diff),
           cor_with_truth = cor(d$diff, d$diff_true), coefs = coefs)

saveRDS(list(table = tab, venue_means = vm_all, ba = ba), "results/platform_python.rds")
print(tab, digits = 3); print(coefs, digits = 2)
cat("Bland-Altman：估計偏誤與真實偏誤的相關", ba$cor_with_truth, "\n")
