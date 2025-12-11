##conda evn
activate test1126



git clone https://github.com/microsoft/markitdown.git
cd markitdown
pip install "markitdown[all]" 


##usage pdf to filename.md
markitdown path-to-file.pdf -o document.md

markitdown 台塑2024_TCFD_target.pdf -o 台塑2024_TCFD_target.md


markitdown 2024-ESG-Performance-Metrics.pdf -o 2024-ESG-Performance-Metrics.md


##跑網頁
streamlit run app.py