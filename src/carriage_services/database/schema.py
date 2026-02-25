from sqlalchemy import inspect

from carriage_services.database.session import engine


def display_schema() -> None:
    """Retrieves and displays the current database schema."""
    print("--- Database Schema ---")
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    if not table_names:
        print("No tables found in the database.")
        return

    for table_name in table_names:
        print(f"\n[Table: {table_name}]")
        columns = inspector.get_columns(table_name)
        foreign_keys = inspector.get_foreign_keys(table_name)

        fk_map = {}
        for fk in foreign_keys:
            for col_name in fk["constrained_columns"]:
                fk_map[col_name] = f"{fk['referred_table']}({', '.join(fk['referred_columns'])})"

        for column in columns:
            col_info = f"  - {column['name']} ({column['type']})"
            if column.get("primary_key"):
                col_info += " [PK]"
            if column["name"] in fk_map:
                col_info += f" [FK -> {fk_map[column['name']]}]"
            print(col_info)

    print("\n--- End of Schema ---")
