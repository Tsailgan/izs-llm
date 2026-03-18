NF_TEMPLATE_AST = """
nextflow.enable.dsl=2

// --- IMPORTS ---
{% for imp in imports %}
include { {{ imp.functions | join('; ') }} } from '{{ imp.module_path }}'
{% endfor %}

// --- GLOBALS ---
{% for g in globals %}
{% if g.type == 'string' %}
def {{ g.name }} = "{{ g.value }}"
{% else %}
def {{ g.name }} = {{ g.value }}
{% endif %}
{% endfor %}

// --- INLINE PROCESSES ---
{% for proc in inline_processes %}
process {{ proc.name }} {
{% if proc.container %}    container "{{ proc.container }}"{% endif %}
    tag "${md?.cmp}/${md?.ds}/${md?.dt}"
{% if proc.input_declarations %}
    input:
{% for inp in proc.input_declarations %}        {{ inp }}
{% endfor %}
{% endif %}
{% if proc.output_declarations %}
    output:
{% for out in proc.output_declarations %}        {{ out }}
{% endfor %}
{% endif %}

    script:
'''
{{ proc.script_block | safe }}
'''
}
{% endfor %}

// --- WORKFLOW MACRO ---
{% macro render_workflow(wf_obj) %}
workflow {{ wf_obj.name }} {
{% if wf_obj.take_channels %}
    take:
{% for channel in wf_obj.take_channels %}
        {{ channel }}
{% endfor %}
{% endif %}

    main:
    {{ wf_obj.body_code | safe }}

{% if wf_obj.emit_channels %}
    emit:
{% for emit in wf_obj.emit_channels %}
        {{ emit }}
{% endfor %}
{% endif %}
}
{% endmacro %}

// --- HELPER SUB-WORKFLOWS ---
{% for sub in sub_workflows %}
{{ render_workflow(sub) }}
{% endfor %}

// --- MAIN WORKFLOW MODULE ---
{{ render_workflow(main_workflow) }}

// --- ENTRYPOINT WORKFLOW ---
workflow {
    {{ entrypoint.body_code | safe }}
}
"""