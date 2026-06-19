# Instantiates Celery(), configures Redis broker/result backend from settings, 
# registers the beat_schedule (3 AM daily consolidation, periodic decay refresh)