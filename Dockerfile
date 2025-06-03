# Use an official Python base image
FROM python:3.13.3-slim

# Set the working directory in the container
WORKDIR /app

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project into the container
COPY . .

# Expose the application port
EXPOSE 10002

# Set the entrypoint command to run the application
CMD ["python", "-m", "agent", "--host", "0.0.0.0", "--port", "10002"]