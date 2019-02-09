import os

# pip install snakeviz
os.system("py -3.6 -m cProfile -o profile.prof Main.py")
os.system("snakeviz profile.prof")
