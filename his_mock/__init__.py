"""The mock Indian hospital (HIS, LIS, RIS, PACS) for the Vaidyx-TB V2 demo and tests: SYNTHETIC data only.

A separate app with its own store in data/his_mock/ (gitignored, rebuilt from a seed). Vaidyx-TB never imports this package;
it reads the mock only through tumour_board/his_client.py, as it would read a real hospital's HIS.
"""
