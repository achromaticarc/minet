# Cleanup
rm -rf ftest/content
rm -f ftest/report.csv

# Fetching url from csv file
python -m minet.cli fetch url ftest/resources/urls.csv \
  -O ftest/content \
  --filename id \
  --folder-strategy normalized-hostname \
  --grab-cookies firefox \
  --compress \
  -s id,url \
  -t 25 > ftest/report.csv
