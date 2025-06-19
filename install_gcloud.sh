#!/bin/bash

echo "📦 Installing Google Cloud SDK..."
curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-471.0.0-linux-x86_64.tar.gz
tar -xf google-cloud-cli-*.tar.gz
./google-cloud-sdk/install.sh
exec -l $SHELL

echo "✅ Google Cloud SDK installed. Run: gcloud init"
