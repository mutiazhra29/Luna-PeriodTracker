import tkinter as tk

from luna_core.app import LunaApp
from luna_core.database import LunaDatabase
from luna_core.paths import database_path


def main() -> None:
    root = tk.Tk()
    database = LunaDatabase(database_path())
    try:
        LunaApp(root, database)
        if root.winfo_exists():
            root.mainloop()
    finally:
        database.close()


if __name__ == "__main__":
    main()
