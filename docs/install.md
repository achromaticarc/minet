# How to Install minet from scratch

## Summary

* [macOS](macOS)

## macOS

1. Open a shell and type `git --version`. If this works, go to `2.`. Else your shell will prompt you to install command line tools. Just accept and wait for those to install. If nothing happens, try and run `xcode-select --install` instead.
2. If you don't have homebrew, install it using this [documentation](https://brew.sh/index_fr).
3. Run `brew update` then `brew install readline xz`.
4. Install pyenv using this [documentation](https://github.com/pyenv/pyenv-installer#install). Don't forget to heed pyenv advices by the end of the installation and to add the relevant lines to your `.bashrc` or `.profile` file.
5. Install python v3.7.10 using pyenv (or any newer version you may like): `pyenv install 3.7.10`.
6. Create a virtualenv for your minet endeavors: `pyenv virtualenv 3.7.10 minet`.
7. Activate it `pyenv activate minet`.
8. Install `minet` using pip: `pip install minet`.
9.  Finally, test that everything went smoothly by testing `minet --version`.
