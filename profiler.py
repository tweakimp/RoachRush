import os

# pip install snakeviz
# run game and create a profile
os.system("py -3.7 -m cProfile -o profile.prof Main.py")
# watch it in snakeviz
os.system("snakeviz profile.prof")
