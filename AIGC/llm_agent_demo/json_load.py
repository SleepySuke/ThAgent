from langchain_community.document_loaders import JSONLoader
json_loader = JSONLoader(
    file_path = './json_data/sample.json',
    jq_schema= '.name',
    text_content=False,
)




data = json_loader.load()
for d in data:
    print(d.page_content)


loader = JSONLoader(

    file_path='./json_data/products.jsonl',
    jq_schema='.name',
    text_content=False,
    json_lines=True

)

jl = loader.load()
for d in jl:
    print(d.page_content)