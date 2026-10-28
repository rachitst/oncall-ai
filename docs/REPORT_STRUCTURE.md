# ESE mini-project report — required structure (10–15 pages, college format as in Exp 4–7 docs)

1. **Title page** — project title, name, UID, course, semester, institute, GitHub + live demo links
2. **Index**
3. **Abstract** — problem, approach (QLoRA classifier + RAG runbooks + LangGraph + FastAPI/cloud LLM deployment), key results
4. **Introduction** — on-call pain, why LLMs, objectives, concepts from Exp 2–7 used
5. **Application workflow** — architecture diagram, LangGraph node diagram, data flow, screenshots of UI (analyze, sources, report, comparison tab), API docs screenshot, deployment screenshot (HF Space), GitHub screenshot
6. **Results / observations** — dataset stats table; 5-way comparison table + charts (accuracy/F1, resources, latency, confusion matrix, loss curves); smoke-test table (health/supported/unknown/validation/405/503); latency breakdown; example analyses; limitations
7. **Conclusion** — what was built, what was learned, future work

Screenshots to capture during the run (save to docs/screenshots/):
- ui_analyze_prod_db.png, ui_sources.png, ui_report.png, ui_lowconfidence.png, ui_comparison_tab.png, ui_architecture_tab.png
- swagger_docs.png, swagger_analyze_200.png, swagger_422.png, swagger_503_wrong_key.png
- hf_space_running.png, hf_space_settings_secrets.png (mask values), hf_model_repo.png
- github_repo.png, colab_training_charts.png, colab_comparison_table.png, terminal_pytest.png, terminal_smoke_test.png
