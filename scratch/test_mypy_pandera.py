import pandera.pandas as pa
from pandera.typing import Series

class LapsSchema(pa.DataFrameModel):
    LapNumber: Series[pa.Int64] = pa.Field(ge=1, le=100)
    SpeedI1: Series[pa.Float64] | None = pa.Field(nullable=True, ge=0, le=450)
