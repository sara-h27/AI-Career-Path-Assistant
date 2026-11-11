# Ranking evaluation (Section 10.2)

| Resume | Method | P@5 | nDCG@10 |
|---|---|---|---|
| r1_data_analyst_junior | keyword_baseline | 0.80 | 0.685 |
| r1_data_analyst_junior | hybrid_no_dense | 0.80 | 0.810 |
| r1_data_analyst_junior | rag_hybrid (default) | 1.00 | 0.808 |
| r2_backend_python | keyword_baseline | 0.20 | 0.413 |
| r2_backend_python | hybrid_no_dense | 0.40 | 0.598 |
| r2_backend_python | rag_hybrid (default) | 0.20 | 0.721 |
| r3_accountant | keyword_baseline | 1.00 | 0.814 |
| r3_accountant | hybrid_no_dense | 1.00 | 0.793 |
| r3_accountant | rag_hybrid (default) | 1.00 | 0.794 |
| **mean** | **keyword_baseline** | **0.67** | **0.637** |
| **mean** | **hybrid_no_dense** | **0.73** | **0.733** |
| **mean** | **rag_hybrid (default)** | **0.73** | **0.774** |

Qdrant retrieval stage, Recall@40 of relevant postings over all 143 postings: r1_data_analyst_junior 1.00, r2_backend_python 1.00, r3_accountant 0.90

Pools and graded labels: `data/eval/labels.json`.
