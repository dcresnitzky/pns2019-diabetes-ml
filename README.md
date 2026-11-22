# Interpretable machine learning and self-reported diabetes — PNS 2019

> **Resumo em português.** Código da análise de um artigo de mestrado (Mestrado Profissional em Telessaúde, UERJ) que investiga características demográficas, socioeconômicas, comportamentais e de saúde associadas ao diagnóstico médico autorreferido de diabetes em adultos brasileiros, com dados da Pesquisa Nacional de Saúde 2019 (IBGE). Compara Regressão Logística, Random Forest e XGBoost e usa SHAP para interpretar os modelos. As instruções para reproduzir estão abaixo.

Analysis code for a master's research article that examines demographic, socioeconomic, behavioral and health characteristics associated with self-reported medical diagnosis of diabetes among Brazilian adults. The data come from the 2019 Brazilian National Health Survey (Pesquisa Nacional de Saúde, PNS 2019, IBGE). The study compares Logistic Regression, Random Forest and XGBoost and uses SHAP to interpret the models.

> The outcome is a **self-reported diagnosis** in a **cross-sectional** survey. Results describe associations and should not be read as causal relationships or as a clinical diagnostic tool.

The code, comments and figure labels are in Portuguese.

## Structure

```
scripts/baixar_dados.py             downloads the official IBGE microdata and checks SHA-256 hashes
src/pns_utils.py                    reads the layout/dictionary, derives variables, survey-design estimation
notebooks/diabetes_pns2019.ipynb    full analysis: data, exploration, models and SHAP
data/                               (not tracked) raw/, extracted/, processed/
figures/                            (not tracked) created when the notebook runs
```

## How to reproduce

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/baixar_dados.py          # ~30 MB compressed, ~455 MB extracted
cd notebooks && ../.venv/bin/jupyter nbconvert --to notebook --execute --inplace diabetes_pns2019.ipynb
```

Requires Python 3.12. IBGE file versions: microdata from 2022-05-25 (`PNS_2019_20220525.zip`) and dictionary from 2022-05-30 (`Dicionario_e_input_20220530.zip`). The SHA-256 hashes are in `scripts/baixar_dados.py`.

## Methodological decisions

- **Population**: selected residents with a completed individual interview (`M001 = 1`) aged 18 or older: 88,531 adults.
- **Outcome**: `Q03001 = 1`, excluding gestational-only diabetes (`Q03002 = 1`). `Q03001` is only asked of people who have ever had a blood glucose test (`Q02901 ≠ 6`). Those who never had one are counted as non-cases, the same convention that reproduces the official prevalence (7.7%).
- **Survey design**: weight `V00291`, stratum `V0024`, PSU `UPA_PNS` and post-stratification `V00293`/`V00292`. Variance is computed by Taylor linearization in `src/pns_utils.py`. Estimates were validated against Malta et al. (2022).
- **Questionnaire skips** treated as "no diagnosis": hypertension (`Q00101 = 6`) and high cholesterol (`Q05901 = 6`). Exercise less often than weekly counts as 0 minutes.
- **Predictors (20)**: age, sex, race/skin color, region, rural area, education, income, health insurance, BMI, hypertension, high cholesterol, smoking, binge drinking and physical activity.
- **Excluded due to leakage**: diabetes treatment and follow-up (`Q031`–`Q039`), most recent blood glucose test (`Q02901`), heart disease and stroke (possible complications) and self-rated health.
- **Modeling**: pregnant women excluded (no BMI); stratified 80/20 train/test split; 5-fold cross-validation; balanced classes in training; models trained without survey weights.

## Main reference

Malta DC, Bernal RTI, Sá ACMGN, Silva TMR, Iser BPM, Duncan BB, Schmidt MI. Diabetes autorreferido e fatores associados na população adulta brasileira: Pesquisa Nacional de Saúde, 2019. *Ciência & Saúde Coletiva*. 2022;27(7). doi:10.1590/1413-81232022277.02572022

## License

Code released under the [MIT License](LICENSE). PNS 2019 microdata are published by IBGE and are not redistributed here.
