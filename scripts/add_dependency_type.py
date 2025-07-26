#!/usr/bin/env python3
"""
Add dependency_type column to TaskDependency table
"""

import sqlite3
import sys
from pathlib import Path

def migrate_database(db_path: str = "ai_org.db"):
    """Add dependency_type column if it doesn't exist."""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if dependency_type column exists
        cursor.execute("PRAGMA table_info(taskdependency)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'dependency_type' not in columns:
            print("Adding dependency_type column...")
            cursor.execute("""
                ALTER TABLE taskdependency 
                ADD COLUMN dependency_type VARCHAR(50) NOT NULL DEFAULT 'blocks'
            """)
            conn.commit()
            print("✓ dependency_type column added successfully")
        else:
            print("✓ dependency_type column already exists")
            
    except sqlite3.Error as e:
        print(f"Error during migration: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
