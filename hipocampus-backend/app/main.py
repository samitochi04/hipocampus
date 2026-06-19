# Creates the FastAPI() instance, registers CORS middleware (credentials=True for cookie auth), mounts the v1 router, 
# defines startup event (open DB engine, open Redis pool, instantiate Qwen client) and shutdown event 
# (close all connections gracefully)