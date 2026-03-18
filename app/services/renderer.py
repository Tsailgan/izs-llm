from jinja2 import Template
from app.services.graph_state import GraphState
from app.utils.rendering import NF_TEMPLATE_AST

def render_nextflow_code(ast) -> str:
    if hasattr(ast, 'model_dump'):
        data = ast.model_dump()
    elif hasattr(ast, 'dict'):
        data = ast.dict()
    else:
        data = ast

    # Render Template
    t = Template(NF_TEMPLATE_AST)
    rendered = t.render(**data)
    
    # Clean up excess whitespace
    while "\n\n\n" in rendered:
        rendered = rendered.replace("\n\n\n", "\n\n")
        
    return rendered.strip()

def renderer_node(state: GraphState):
    print("--- [NODE] RENDERER ---")

    if state.get("error"): return {}

    raw_ast = state.get('ast_json', {})
    
    try:
        nf_code = render_nextflow_code(raw_ast)
    except Exception as e:
        print(f"💥 NEXTFLOW RENDERER CRASH: {e}")
        return {"error": f"Nextflow Code Generation Failed: {str(e)}"}

    return {
        "nextflow_code": nf_code
    }