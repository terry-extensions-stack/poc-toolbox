from celery import Celery

from poc_toolbox.config.podcast import PodcastSettings

celery_app = Celery('podcasts', broker=PodcastSettings().broker_url)
celery_app.conf.update(
    task_ignore_result=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
