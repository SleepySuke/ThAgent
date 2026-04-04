from langchain_community.document_loaders import CSVLoader

csv_loader = CSVLoader(file_path="./csv_data/orders.csv",encoding="utf-8",csv_args={"delimiter":"|"})
data = csv_loader.load()
for d in data:
    print(d.page_content)