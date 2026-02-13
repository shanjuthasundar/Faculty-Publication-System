# Faculty Publication System - ER Diagram

```mermaid
erDiagram
    FACULTIES {
        INTEGER id PK
        TEXT name
        TEXT email UNIQUE
        TEXT password_hash
        TEXT password_salt
        TEXT created_at
    }

    SESSIONS {
        TEXT token PK
        INTEGER faculty_id FK
        TEXT expires_at
        TEXT created_at
    }

    PUBLICATIONS {
        INTEGER id PK
        INTEGER faculty_id FK
        TEXT title
        TEXT authors
        TEXT venue
        TEXT pub_type
        TEXT published_date
        TEXT content
        TEXT doi
        TEXT file_name
        TEXT file_type
        BLOB file_data
        TEXT created_at
    }

    FACULTIES ||--o{ SESSIONS : has
    FACULTIES ||--o{ PUBLICATIONS : creates
```

