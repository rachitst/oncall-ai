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
- modal_app_running.png (live demo; HF Spaces needs PRO for Docker on CPU), modal_secret.png (mask values), hf_model_repo.png
- github_repo.png, terminal_pytest.png, terminal_smoke_test.png
- from the executed notebook (training/OnCall_AI_Training.ipynb via nbconvert + Playwright): colab_step3_env_dataset.png, colab_step7_groq.png,
  colab_step10_lora_training.png, colab_step11_qlora_training.png, colab_comparison_table.png, colab_step13_merge_push.png
- charts copied from results/figures/: chart_type_accuracy_f1.png, chart_severity_accuracy_f1.png, chart_training_resources.png,
  chart_inference_latency_memory.png, chart_confusion_matrix.png, chart_loss_curves.png
