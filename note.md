##conda evn
activate test1126


##usage pdf to filename.md
markitdown path-to-file.pdf -o document.md

markitdown 2024-ESG-Performance-Metrics.pdf -o 2024-ESG-Performance-Metrics.md

markitdown pdf\中油2024.pdf -o pdf\中油2024.md

##跑網頁
streamlit run app.py


##診斷

python tools/diagnose_pdf.py D:\碩一\金融科技\比賽\pdf\中油2024.pdf
##部署
https://github.com/hsuan619/fintech_esg.git