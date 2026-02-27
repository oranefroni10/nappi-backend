#!/usr/bin/env python3
"""Generate Pydantic models from database schema. Run when schema changes."""
import asyncio
import asyncpg
from pathlib import Path
from app.core.settings import settings

async def generate_pydantic_models():
    db_url = settings.DATABASE_URL.replace("+asyncpg", "")
    conn = await asyncpg.connect(db_url)

    try:
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'Nappi'
            ORDER BY table_name
        """)

        output = []
        output.append("# Generated from database schema - DO NOT EDIT MANUALLY")
        output.append("# Run 'python generate_models.py' to regenerate")
        output.append("")
        output.append("from pydantic import BaseModel, Field")
        output.append("from datetime import datetime, date")
        output.append("from typing import Optional")
        output.append("from decimal import Decimal")
        output.append("\n")

        for table in tables:
            table_name = table['table_name']

            columns = await conn.fetch("""
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    column_default,
                    character_maximum_length,
                    numeric_precision,
                    numeric_scale
                FROM information_schema.columns
                WHERE table_schema = 'Nappi' AND table_name = $1
                ORDER BY ordinal_position
            """, table_name)

            class_name = ''.join(word.capitalize() for word in table_name.split('_'))

            output.append(f"class {class_name}(BaseModel):")
            output.append(f'    """')
            output.append(f'    Represents the Nappi.{table_name} table')
            output.append(f'    """')

            for col in columns:
                col_name = col['column_name']
                data_type = col['data_type']
                nullable = col['is_nullable'] == 'YES'
                has_default = col['column_default'] is not None

                type_map = {
                    'bigint': 'int',
                    'integer': 'int',
                    'smallint': 'int',
                    'real': 'float',
                    'double precision': 'float',
                    'numeric': 'Decimal',
                    'character varying': 'str',
                    'character': 'str',
                    'text': 'str',
                    'timestamp without time zone': 'datetime',
                    'timestamp with time zone': 'datetime',
                    'date': 'date',
                    'time without time zone': 'str',
                    'time with time zone': 'str',
                    'boolean': 'bool',
                    'json': 'dict',
                    'jsonb': 'dict',
                    'uuid': 'str',
                    'bytea': 'bytes',
                }

                python_type = type_map.get(data_type, 'str')

                if nullable or has_default:
                    if col_name == 'id' and has_default:
                        # Primary key with default (auto-increment) - optional on create
                        output.append(f"    {col_name}: Optional[{python_type}] = None")
                    elif has_default:
                        output.append(f"    {col_name}: Optional[{python_type}] = None")
                    else:
                        output.append(f"    {col_name}: Optional[{python_type}] = None")
                else:
                    output.append(f"    {col_name}: {python_type}")

            output.append("")
            output.append("    class Config:")
            output.append("        from_attributes = True")
            output.append("        json_encoders = {")
            output.append("            datetime: lambda v: v.isoformat() if v else None,")
            output.append("            date: lambda v: v.isoformat() if v else None,")
            output.append("        }")
            output.append("\n")

        script_dir = Path(__file__).parent
        output_path = script_dir / 'models.py'

        with open(output_path, 'w') as f:
            f.write('\n'.join(output))

        print(f"Successfully generated {len(tables)} models in {output_path}")
        print(f"\nGenerated models:")
        for table in tables:
            class_name = ''.join(word.capitalize() for word in table['table_name'].split('_'))
            print(f"  - {class_name} (from Nappi.{table['table_name']})")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(generate_pydantic_models())
