# =============================================================================
# 套用到 Python 模擬器產生的野場資料（/mnt/project-files/volley-sim，種子 20261126）
# 這份資料的產生機制跟模型「不一樣」（逐球模擬發球、攻擊、攔網，默契稀疏、
# 人數不足扣分），所以是比較誠實的「模型設定不完全正確」測試。
# 輸出 ratings / pairs CSV，給 Python 分隊原型當輸入。
# =============================================================================
source("R/rating_model.R"); source("R/read_volley_sim.R")
SIM_DIR <- Sys.getenv("VOLLEY_SIM_DIR", "/mnt/project-files/volley-sim")
vs <- read_volley_sim(SIM_DIR)

fits <- list(
  M1_個人 = fit_rating_model(vs$games, vs$players, use_level = FALSE, use_pairs = FALSE),
  M2_個人加自報先驗 = fit_rating_model(vs$games, vs$players, use_level = TRUE, use_pairs = FALSE),
  M3_完整含搭檔 = fit_rating_model(vs$games, vs$players, use_level = TRUE, use_pairs = TRUE)
)
tp <- vs$truth$players
cmp <- do.call(rbind, lapply(names(fits), function(nm) {
  r <- fits[[nm]]$ratings; t <- tp$theta_true[match(r$player, tp$player)]
  data.frame(method = nm, spearman = cor(r$theta, t, method = "spearman"),
             pearson = cor(r$theta, t), sigma = fits[[nm]]$sigma, tau = fits[[nm]]$tau,
             delta = if (fits[[nm]]$use_size) fits[[nm]]$delta else NA)
}))
lv <- vs$players$level[match(tp$player, vs$players$player)]
cmp <- rbind(data.frame(method = "B1_自報程度", spearman = cor(lv, tp$theta_true, method = "spearman"),
                        pearson = cor(lv, tp$theta_true), sigma = NA, tau = NA, delta = NA), cmp)

# 涵蓋率：真值與模型尺度不同（真值是 Python 模擬器的 skill 尺度），
# 先用線性迴歸把真值換到模型的 logit 尺度，再看 95% 區間涵蓋率（僅供參考）
best <- fits$M2_個人加自報先驗
r <- best$ratings; r$theta_true <- tp$theta_true[match(r$player, tp$player)]
k <- coef(lm(theta ~ theta_true, data = r))
r$truth_on_model_scale <- k[1] + k[2] * r$theta_true
coverage_rescaled <- mean(r$lower < r$truth_on_model_scale & r$truth_on_model_scale < r$upper)

# 搭檔：真值是稀疏的默契（10% 非零）
pf <- fits$M3_完整含搭檔$pairs
ch <- vs$truth$pairs
pf$chemistry <- ch$chemistry[match(pf$pair, ch$pair)]; pf$chemistry[is.na(pf$chemistry)] <- 0

dir.create("output", showWarnings = FALSE)
write.csv(best$ratings, "output/ratings_volley_sim.csv", row.names = FALSE)
write.csv(fits$M3_完整含搭檔$pairs, "output/pairs_volley_sim.csv", row.names = FALSE)
saveRDS(list(cmp = cmp, ratings = r, coverage_rescaled = coverage_rescaled, pairs = pf,
             fits = lapply(fits, function(f) f[c("ratings", "pairs", "sigma", "tau", "beta",
                                                 "beta_se", "delta", "delta_se", "lml")]),
             n_games = nrow(vs$games), n_players = nrow(vs$players),
             n_played = sum(r$sets > 0)),
        "results/volley_sim.rds")
print(cmp, digits = 3); cat("rescaled coverage", coverage_rescaled, "\n")
print(fits$M3_完整含搭檔)
