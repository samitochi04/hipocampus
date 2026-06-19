# query_expansion() (Qwen-Max generates semantic query variants), 
# parallel_vector_search() (runs the 3 pgvector queries against episodes/semantic_facts/procedural_patterns concurrently), 
# rank_and_fold() (dedupe + confidence threshold + fold into [MEMORY_CONTEXT]), context_window_safe() (token-budgets the final block)