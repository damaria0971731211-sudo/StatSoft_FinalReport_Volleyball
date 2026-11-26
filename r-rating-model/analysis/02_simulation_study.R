# =============================================================================
# 模擬研究：已知真實實力時，模型能否估回？95% 區間涵蓋率是否接近 95%？
# 需要幾晚的資料？自報程度先驗、搭檔效果有沒有幫助？
# 每個情境重複 R 次；每次另外模擬 4 晚作為「未來」測試資料，評估預測能力。
# =============================================================================
source("R/rating_model.R"); source("R/simulate.R")
library(parallel)
R_REPS <- as.integer(Sys.getenv("R_REPS", "50"))
N_TEST_NIGHTS <- 4

scenarios <- rbind(
  data.frame(name = "base", n_nights = c(4, 8, 16, 32), sigma = 0.5, tau = 0.3,
             level_cor = 0.7, formation = "random"),
  data.frame(name = c("自報相關低 r=0.3", "依自報程度分隊", "實力差異小 σ=0.3", "無搭檔效果 τ=0"),
             n_nights = 16, sigma = c(0.5, 0.5, 0.3, 0.5), tau = c(0.3, 0.3, 0.3, 0),
             level_cor = c(0.3, 0.7, 0.7, 0.7), formation = c("random", "level", "random", "random"))
)

one_rep <- function(sc, rep) {
  seed <- 1000 * as.integer(factor(sc$name, levels = unique(scenarios$name))) + 10 * sc$n_nights + rep
  set.seed(seed)
  truth <- simulate_players(40, sigma = sc$sigma, tau = max(sc$tau, 1e-9), level_cor = sc$level_cor)
  if (sc$tau == 0) truth$pairs$gamma <- 0
  all <- simulate_league(truth, sc$n_nights + N_TEST_NIGHTS, formation = sc$formation)
  train <- all[all$night <= sc$n_nights, ]; test <- all[all$night > sc$n_nights, ]
  pl <- truth$players
  info <- pl[, c("player", "level")]

  fits <- list(
    M1_個人 = fit_rating_model(train, info, use_level = FALSE, use_pairs = FALSE),
    M2_個人加自報先驗 = fit_rating_model(train, info, use_level = TRUE, use_pairs = FALSE),
    M3_完整含搭檔 = fit_rating_model(train, info, use_level = TRUE, use_pairs = TRUE)
  )
  rows <- list()
  # 基準方法 1：自報程度；基準方法 2：原始得分率
  d <- build_design(train, info)
  pts_for <- as.numeric(crossprod(abs(d$X) > 0 & d$X > 0, train$score_a) +
                        crossprod(abs(d$X) > 0 & d$X < 0, train$score_b))
  pts_tot <- as.numeric(crossprod(abs(d$X) > 0, train$score_a + train$score_b))
  share <- ifelse(pts_tot > 0, pts_for / pts_tot, 0.5)
  tt <- pl$theta_true[match(d$ids, pl$player)]
  base <- list(B1_自報程度 = pl$level[match(d$ids, pl$player)], B2_原始得分率 = share)
  for (nm in names(base)) rows[[nm]] <- data.frame(method = nm,
    spearman = suppressWarnings(cor(base[[nm]], tt, method = "spearman")),
    rmse = NA, coverage = NA, width = NA, test_logloss = NA, pair_cor = NA, pair_cov = NA,
    sigma_hat = NA, tau_hat = NA, beta_hat = NA)

  for (nm in names(fits)) {
    f <- fits[[nm]]
    r <- f$ratings; th <- pl$theta_true[match(r$player, pl$player)]; th <- th - mean(th)
    pr <- sapply(seq_len(nrow(test)), function(i) predict_set(f,
      strsplit(test$team_a[i], ";")[[1]], strsplit(test$team_b[i], ";")[[1]], test$target[i])["p_set"])
    y <- as.integer(test$score_a > test$score_b)
    pc <- pcov <- NA
    if (!is.null(f$pairs) && sc$tau > 0) {
      gt <- truth$pairs$gamma[match(f$pairs$pair, truth$pairs$pair)]
      pc <- cor(f$pairs$gamma, gt); pcov <- mean(f$pairs$lower < gt & gt < f$pairs$upper)
    }
    rows[[nm]] <- data.frame(method = nm,
      spearman = cor(r$theta, th, method = "spearman"),
      rmse = sqrt(mean((r$theta - th)^2)),
      coverage = mean(r$lower < th & th < r$upper),
      width = mean(r$upper - r$lower),
      test_logloss = -mean(y * log(pr) + (1 - y) * log(1 - pr)),
      pair_cor = pc, pair_cov = pcov,
      sigma_hat = f$sigma, tau_hat = f$tau, beta_hat = if (f$use_level) f$beta else NA)
  }
  out <- do.call(rbind, rows)
  cbind(scenario = sc$name, n_nights = sc$n_nights, sets = nrow(train), rep = rep, out,
        mean_margin = mean(abs(train$score_a - train$score_b)))
}

jobs <- expand.grid(s = seq_len(nrow(scenarios)), rep = seq_len(R_REPS))
t0 <- Sys.time()
res <- mclapply(seq_len(nrow(jobs)), function(j) {
  tryCatch(one_rep(scenarios[jobs$s[j], ], jobs$rep[j]),
           error = function(e) { message("fail ", j, ": ", conditionMessage(e)); NULL })
}, mc.cores = max(1, detectCores()), mc.preschedule = FALSE)
res <- do.call(rbind, res)
cat("完成", nrow(jobs), "次重複，耗時", format(Sys.time() - t0), "\n")
saveRDS(list(results = res, scenarios = scenarios, R_REPS = R_REPS), "results/simulation_study.rds")
agg <- aggregate(cbind(spearman, rmse, coverage, width, test_logloss, pair_cor, pair_cov) ~
                   scenario + n_nights + method, data = res, FUN = mean, na.action = na.pass)
print(agg[order(agg$scenario, agg$n_nights, agg$method), ], digits = 3)
