from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr


class RSSArticle(BaseModel):
    model_config = ConfigDict(extra='ignore', hide_input_in_errors=True)
    id: UUID
    publish_at: StrictInt | None = None
    link: StrictStr | None = None
    title: StrictStr | None = None
    cover: StrictStr | None = None
    is_copyright: StrictBool | None = None
    feed_name: StrictStr | None = None
    feed_cover: StrictStr | None = None


class RSSArticleBatch(BaseModel):
    items: list[RSSArticle]
