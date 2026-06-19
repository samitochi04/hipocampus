# process_turn(payload, user): pushes message to redis_buffer, calls tier_retrieval.retrieve_all_tiers(), 
# assembles final prompt (system + memory_context + user message), calls qwen_router.generate(), 
# pushes reply back to redis_buffer, calls importance.score_importance() and writes the episode row, returns the response payload