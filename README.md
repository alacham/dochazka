# Attendance System

A simple web-based employee attendance tracking system built with Flask.

## Features

- **Employee Management**: Add, enable/disable employees
- **Clock In/Out**: Simple interface for recording attendance
- **Reports**: View and filter attendance records
- **CSV Export**: Export attendance data to CSV files
- **Security**: HTTP Basic Authentication protection
- **Timezone Support**: All timestamps in Central European Time (Prague)

## Quick Start with Docker

### Prerequisites
- Docker and Docker Compose installed on your system

### Running the Application

1. **Clone or download the project files**

2. **Start the application:**
   ```bash
   docker-compose up -d
   ```

3. **Access the application:**
   - Open your browser and go to: http://localhost:5000
   - Login with: username `admin`, password `password`

4. **Stop the application:**
   ```bash
   docker-compose down
   ```

### Data Persistence

The database is stored in the `./data` directory on your host machine, so your attendance records will persist even if you restart or rebuild the Docker container.

### Configuration

#### For Local Development:
1. **Copy the config template:**
   ```bash
   cp config.example.py config.py
   ```
2. **Edit `config.py`** to set your credentials, port, and other settings

#### For Docker Deployment:
1. **Copy the environment template:**
   ```bash
   cp .env.example .env
   ```
2. **Edit `.env`** to set your credentials, ports, and other settings
3. **Update docker-compose.yml** to use `.env` instead of `.env.example`

#### Port Configuration Examples:

**Local Development (different port):**
```python
# In config.py
PORT = 8080
HOST = "127.0.0.1"
```

**Docker (behind reverse proxy):**
```bash
# In .env
PORT=5000          # Internal container port
HOST_PORT=8080     # External host port
HOST=0.0.0.0       # Listen on all interfaces
```

**Quick Docker port change:**
```bash
HOST_PORT=8080 docker-compose up -d
```

### Default Credentials

- **Username:** admin
- **Password:** password

⚠️ **Important:** Change these credentials before deploying to production!

## Manual Installation (without Docker)

If you prefer to run without Docker:

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Initialize the database:**
   ```bash
   python -c "from app import init_db; init_db()"
   ```

3. **Run the application:**
   ```bash
   python app.py
   ```

4. **Access at:** http://localhost:5000

## Usage

### For Employees
1. Go to the home page
2. Click on your name
3. Click "Enter" when arriving or "Leave" when departing
4. You'll be redirected back to the home page

### For Administrators
1. Go to "Admin & Reports" from the home page
2. **View Reports:** See attendance records with date filtering
3. **Export Data:** Download CSV reports
4. **Manage Employees:** Add new employees or enable/disable existing ones

## File Structure

```
attendance-system/
├── app.py                  # Main Flask application
├── schema.sql              # Database schema
├── config.example.py       # Configuration template for local development
├── config.py               # Local configuration (gitignored)
├── .env.example            # Environment template for Docker
├── .env                    # Docker environment variables (gitignored)
├── generate_secret_key.py  # Utility to generate secure secret keys
├── templates/              # HTML templates
│   ├── base.html
│   ├── home.html
│   ├── action.html
│   └── admin.html
├── Dockerfile              # Docker configuration
├── docker-compose.yml      # Docker Compose configuration
├── requirements.txt        # Python dependencies
├── .gitignore              # Git ignore rules
├── .dockerignore           # Docker ignore rules
└── data/                   # Database storage (created automatically, gitignored)
```

## Security Configuration

### Production Deployment Checklist:
- [ ] Change default username/password in `config.py` or `.env`
- [ ] Set a strong `SECRET_KEY` (use `python -c "import secrets; print(secrets.token_hex(32))"`)
- [ ] Set `DEBUG=false` in production
- [ ] Use HTTPS in production (configure reverse proxy)
- [ ] Backup your database regularly
- [ ] Keep the `config.py` and `.env` files secure and never commit them

### Configuration Files:
- **`config.py`** - Local development configuration (ignored by git)
- **`.env`** - Docker environment variables (ignored by git)  
- **`config.example.py`** - Template for local config
- **`.env.example`** - Template for Docker environment

## Development

To modify the application:

1. Edit the source files
2. Rebuild the Docker image: `docker-compose build`
3. Restart: `docker-compose up -d`

For development with auto-reload, run locally instead of Docker:
```bash
python app.py
```