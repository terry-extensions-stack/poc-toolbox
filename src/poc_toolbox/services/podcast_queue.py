from celery import Celery

from poc_toolbox.config.podcast import PodcastSettings

celery_app = Celery('podcasts', broker=PodcastSettings().broker_url)
celery_app.conf.update(
    task_ignore_result=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    imports=(
        'poc_toolbox.services.podcast_renders.tasks',
        'poc_toolbox.services.podcast_renders.conversion',
        'poc_toolbox.services.podcast_renders.recovery',
    ),
    beat_schedule={'recover-podcast-saves': {'task': 'podcasts.recover', 'schedule': 60.0}},
)
