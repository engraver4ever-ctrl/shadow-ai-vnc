FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY shadow-ai-vnc.py /app/
COPY vnc_skill.py /app/

# Make scripts executable
RUN chmod +x /app/shadow-ai-vnc.py /app/vnc_skill.py

# Create symlinks for easy access
RUN ln -s /app/shadow-ai-vnc.py /usr/local/bin/shadow-ai-vnc \
    && ln -s /app/vnc_skill.py /usr/local/bin/shadow-ai-vnc-skill

ENTRYPOINT ["shadow-ai-vnc"]
CMD ["--help"]
