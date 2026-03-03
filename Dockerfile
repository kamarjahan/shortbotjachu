# Use a lightweight Python base image
FROM python:3.11-slim

# Hugging Face Spaces require running as a non-root user (UID 1000)
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

# Set the working directory
WORKDIR /app

# Copy requirements first to cache the pip install step
COPY --chown=user requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your bot code
COPY --chown=user . /app/

# Expose port 7860 (The default port Hugging Face looks for)
EXPOSE 7860

# Command to run the bot
CMD ["python", "bot.py"]
