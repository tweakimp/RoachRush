import os
import zipfile


def zipdir(path, ziph):
    # ziph is zipfile handle
    for root, _, files in os.walk(path):
        for file in files:
            ziph.write(os.path.join(root, file))


if __name__ == "__main__":
    # create a zip file
    zipf = zipfile.ZipFile("RoachRush.zip", "w", zipfile.ZIP_DEFLATED)
    # write sc2 folder
    zipdir("./sc2", zipf)
    single_files = [
        "__init__.py",
        "data",
        "ladderbots.json",
        "LICENSE",
        "Main.py",
        "profiler.py",
        "README.md",
        "run.py",
        "create_ladder_zip.py",
    ]
    # write single files
    for single_file in single_files:
        zipf.write(single_file)
    zipf.close()
