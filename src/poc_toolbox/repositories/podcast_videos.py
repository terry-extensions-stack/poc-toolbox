from sqlalchemy import func, select

from poc_toolbox.db_models.podcast import PodcastJob

PODCAST_UUID_PATTERN = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'


def generated_videos():
    podcast_id = PodcastJob.payload['id'].as_string()
    ranked = (
        select(
            podcast_id.label('id'),
            PodcastJob.id.label('job_id'),
            PodcastJob.payload['article_id'].as_string().label('article_id'),
            PodcastJob.payload['title'].as_string().label('title'),
            PodcastJob.payload['image_url'].as_string().label('image_url'),
            PodcastJob.created_at,
            func.row_number()
            .over(
                partition_by=podcast_id,
                order_by=(PodcastJob.created_at.desc().nulls_last(), PodcastJob.id.desc()),
            )
            .label('position'),
        )
        .where(
            PodcastJob.status == 'SUCCEEDED',
            PodcastJob.output_key.is_not(None),
            PodcastJob.output_key != '',
            podcast_id.regexp_match(PODCAST_UUID_PATTERN),
        )
        .subquery()
    )
    return select(ranked).where(ranked.c.position == 1).subquery()
