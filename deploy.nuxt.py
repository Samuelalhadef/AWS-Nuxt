import subprocess
import sys
import os
import boto3
import time
import mimetypes

# ============ CONFIGURATION ============
BUILD_OUTPUT_DIR = ".output/public"
AWS_REGION = "eu-west-3"

ENVIRONMENTS = {
    "dev": {
        "bucket": os.environ.get("S3_BUCKET_DEV", ""),
        "cloudfront_id": os.environ.get("CLOUDFRONT_DISTRIBUTION_ID_DEV", ""),
        "url": os.environ.get("CLOUDFRONT_URL_DEV", ""),
    },
    "prod": {
        "bucket": os.environ.get("S3_BUCKET_PROD", ""),
        "cloudfront_id": os.environ.get("CLOUDFRONT_DISTRIBUTION_ID_PROD", ""),
        "url": os.environ.get("CLOUDFRONT_URL_PROD", ""),
    },
}
# =======================================

def load_env_file(env_name):
    """Charge les variables depuis .env.dev ou .env.prod."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_file = os.path.join(script_dir, f".env.{env_name}")
    if not os.path.exists(env_file):
        env_file = os.path.join(script_dir, ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())

def run_command(command, description):
    """Execute une commande shell et affiche le resultat."""
    print(f"\n{'='*50}")
    print(f">> {description}")
    print(f"{'='*50}")
    result = subprocess.run(command, shell=True, cwd=os.path.dirname(os.path.abspath(__file__)))
    if result.returncode != 0:
        print(f"ERREUR: {description} a echoue (code {result.returncode})")
        sys.exit(1)
    print(f"OK: {description}")

def get_content_type(file_path):
    """Determine le Content-Type d'un fichier."""
    content_type, _ = mimetypes.guess_type(file_path)
    return content_type or "application/octet-stream"

def clear_s3_bucket(s3_client, bucket_name):
    """Supprime tous les objets du bucket S3."""
    print(f"\n{'='*50}")
    print(f">> Nettoyage du bucket S3: {bucket_name}")
    print(f"{'='*50}")
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket_name):
        objects = page.get("Contents", [])
        if objects:
            delete_keys = [{"Key": obj["Key"]} for obj in objects]
            s3_client.delete_objects(Bucket=bucket_name, Delete={"Objects": delete_keys})
            print(f"  Supprime {len(delete_keys)} objets")
    print("OK: Bucket vide")

def upload_to_s3(s3_client, bucket_name):
    """Upload tous les fichiers du build vers S3."""
    print(f"\n{'='*50}")
    print(f">> Upload vers S3: {bucket_name}")
    print(f"{'='*50}")
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), BUILD_OUTPUT_DIR)
    file_count = 0
    for root, dirs, files in os.walk(base_dir):
        for file_name in files:
            local_path = os.path.join(root, file_name)
            s3_key = os.path.relpath(local_path, base_dir).replace("\\", "/")
            content_type = get_content_type(local_path)
            s3_client.upload_file(
                local_path,
                bucket_name,
                s3_key,
                ExtraArgs={"ContentType": content_type}
            )
            file_count += 1
            print(f"  Upload: {s3_key} ({content_type})")
    print(f"OK: {file_count} fichiers uploades")

def invalidate_cloudfront(cf_client, cloudfront_id):
    """Invalide le cache CloudFront pour que les changements apparaissent immediatement."""
    if not cloudfront_id:
        print("\nATTENTION: Pas d'ID CloudFront configure, cache non invalide.")
        return
    print(f"\n{'='*50}")
    print(f">> Invalidation du cache CloudFront: {cloudfront_id}")
    print(f"{'='*50}")
    response = cf_client.create_invalidation(
        DistributionId=cloudfront_id,
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": ["/*"]},
            "CallerReference": str(time.time())
        }
    )
    invalidation_id = response["Invalidation"]["Id"]
    print(f"OK: Invalidation creee (ID: {invalidation_id})")

def main():
    # Lecture de l'environnement depuis les arguments
    if len(sys.argv) < 2 or sys.argv[1] not in ("dev", "prod"):
        print("Usage: python deploy.nuxt.py <dev|prod>")
        print("  dev  -> deploie sur l'environnement de developpement")
        print("  prod -> deploie sur l'environnement de production")
        sys.exit(1)

    env_name = sys.argv[1]
    load_env_file(env_name)

    # Recharger la config apres le chargement du .env
    config = {
        "bucket": os.environ.get(f"S3_BUCKET_{env_name.upper()}", ""),
        "cloudfront_id": os.environ.get(f"CLOUDFRONT_DISTRIBUTION_ID_{env_name.upper()}", ""),
        "url": os.environ.get(f"CLOUDFRONT_URL_{env_name.upper()}", ""),
    }

    if not config["bucket"]:
        print(f"ERREUR: S3_BUCKET_{env_name.upper()} non defini.")
        print(f"Verifie ton fichier .env.{env_name} ou .env")
        sys.exit(1)

    print("=" * 50)
    print(f"  DEPLOY NUXT -> AWS S3 + CloudFront [{env_name.upper()}]")
    print("=" * 50)
    print(f"  Bucket:     {config['bucket']}")
    print(f"  CloudFront: {config['cloudfront_id']}")
    print(f"  URL:        {config['url']}")

    # 1. Install
    run_command("npm install", "Installation des dependances (npm install)")

    # 2. Build (generate)
    run_command("npm run generate", "Build du projet (npm run generate)")

    # 3. Connexion AWS
    session = boto3.Session(region_name=AWS_REGION)
    s3_client = session.client("s3")
    cf_client = session.client("cloudfront")

    # 4. Clear ancien S3
    clear_s3_bucket(s3_client, config["bucket"])

    # 5. Push sur le S3
    upload_to_s3(s3_client, config["bucket"])

    # 6. Invalidation cache CloudFront
    invalidate_cloudfront(cf_client, config["cloudfront_id"])

    print(f"\n{'='*50}")
    print(f"DEPLOIEMENT [{env_name.upper()}] TERMINE AVEC SUCCES !")
    print(f"URL: {config['url']}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
