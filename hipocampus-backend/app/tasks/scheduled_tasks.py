# The actual @app.task functions (consolidate_user_memory, refresh_decay_weights) that Celery Beat triggers, 
# each looping over active users and calling the matching memory_engine function