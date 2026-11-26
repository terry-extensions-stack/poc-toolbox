from sqlalchemy import BigInteger, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from poc_toolbox.db_models.base import BaseModel


class RSSArticleSnapshot(BaseModel):
    __tablename__ = 'rss_article_snapshots'
    title: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text)
    cover: Mapped[str | None] = mapped_column(Text)
    publish_at: Mapped[int | None] = mapped_column(BigInteger)
    is_copyright: Mapped[bool | None] = mapped_column(Boolean)
    feed_name: Mapped[str | None] = mapped_column(Text)
    feed_cover: Mapped[str | None] = mapped_column(Text)
