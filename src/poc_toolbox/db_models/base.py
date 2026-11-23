from uuid import uuid4

from sqlalchemy import UUID, DateTime, func
from sqlalchemy.orm import declarative_base, mapped_column

ID_COLUMN_SORT_ORDER = -100
CREATED_AT_COLUMN_SORT_ORDER = 100
UPDATED_AT_COLUMN_SORT_ORDER = 101


class CustomBase:
    """
    Customs DB base class
    """

    id = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4, sort_order=ID_COLUMN_SORT_ORDER, comment='主键id.'
    )
    created_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment='Create time.',
        sort_order=CREATED_AT_COLUMN_SORT_ORDER,
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        comment='Update time.',
        sort_order=UPDATED_AT_COLUMN_SORT_ORDER,
    )


BaseModel = declarative_base(cls=CustomBase)
