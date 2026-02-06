import subprocess
import sys
import os
import boto3
import time
import mimetypes

# ============ CONFIGURATION ============
BUCKET_NAME = "nuxtappiimsamuelalhadef"
CLOUDFRONT_DISTRIBUTION_ID = "E18HZEE2NRSQL0"
BUILD_OUTPUT_DIR = ".output/public"
AWS_REGION = "eu-west-3"  # Change si besoin
# =======================================

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

def clear_s3_bucket(s3_client):
    """Supprime tous les objets du bucket S3."""
    print(f"\n{'='*50}")
    print(f">> Nettoyage du bucket S3: {BUCKET_NAME}")
    print(f"{'='*50}")
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET_NAME):
        objects = page.get("Contents", [])
        if objects:
            delete_keys = [{"Key": obj["Key"]} for obj in objects]
            s3_client.delete_objects(Bucket=BUCKET_NAME, Delete={"Objects": delete_keys})
            print(f"  Supprime {len(delete_keys)} objets")
    print("OK: Bucket vide")

def upload_to_s3(s3_client):
    """Upload tous les fichiers du build vers S3."""
    print(f"\n{'='*50}")
    print(f">> Upload vers S3: {BUCKET_NAME}")
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
                BUCKET_NAME,
                s3_key,
                ExtraArgs={"ContentType": content_type}
            )
            file_count += 1
            print(f"  Upload: {s3_key} ({content_type})")
    print(f"OK: {file_count} fichiers uploades")

def invalidate_cloudfront(cf_client):
    """Invalide le cache CloudFront pour que les changements apparaissent immediatement."""
    if not CLOUDFRONT_DISTRIBUTION_ID:
        print("\nATTENTION: Pas d'ID CloudFront configure, cache non invalide.")
        print("Remplis CLOUDFRONT_DISTRIBUTION_ID dans le script pour invalider le cache.")
        return
    print(f"\n{'='*50}")
    print(f">> Invalidation du cache CloudFront: {CLOUDFRONT_DISTRIBUTION_ID}")
    print(f"{'='*50}")
    response = cf_client.create_invalidation(
        DistributionId=CLOUDFRONT_DISTRIBUTION_ID,
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": ["/*"]},
            "CallerReference": str(time.time())
        }
    )
    invalidation_id = response["Invalidation"]["Id"]
    print(f"OK: Invalidation creee (ID: {invalidation_id})")

def main():
    print("=" * 50)
    print("  DEPLOY NUXT -> AWS S3 + CloudFront")
    print("=" * 50)

    # 1. Install
    run_command("npm install", "Installation des dependances (npm install)")

    # 2. Build (generate)
    run_command("npm run generate", "Build du projet (npm run generate)")

    # 3. Connexion AWS
    session = boto3.Session(region_name=AWS_REGION)
    s3_client = session.client("s3")
    cf_client = session.client("cloudfront")

    # 4. Clear ancien S3
    clear_s3_bucket(s3_client)

    # 5. Push sur le S3
    upload_to_s3(s3_client)

    # 6. Invalidation cache CloudFront
    invalidate_cloudfront(cf_client)

    print(f"\n{'='*50}")
    print("DEPLOIEMENT TERMINE AVEC SUCCES !")
    print(f"URL: https://d3da6e1bqcx9pg.cloudfront.net")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
