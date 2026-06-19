# Shared Depends() functions: get_db() yields an async SQLAlchemy session, get_redis() returns the shared Redis client, 
# get_current_user() reads the JWT cookie off the request, decodes it, loads the matching user row, raises 401 
# if missing/invalid/expired