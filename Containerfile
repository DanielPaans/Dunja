# Use the official lightweight Nginx image
FROM docker.io/library/nginx:alpine

# Copy your local index.html into Nginx's default public directory
COPY index.html /usr/share/nginx/html/index.html

COPY images/ /usr/share/nginx/html/images/

# Expose port 80 to allow incoming web traffic
EXPOSE 80