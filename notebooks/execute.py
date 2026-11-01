"""Execute every notebook cell with the isolated project's actual interpreter."""
from pathlib import Path
import json
import os
import sys
import tempfile
import shutil
import nbformat
from nbclient import NotebookClient

ROOT=Path(__file__).resolve().parent
path=ROOT/'ev-scheduling-validation.ipynb'
with tempfile.TemporaryDirectory(prefix='ev-jupyter-') as temp:
    temp=Path(temp)
    kernel=temp/'kernels/ev-sim';kernel.mkdir(parents=True)
    (kernel/'kernel.json').write_text(json.dumps({'argv':[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],'display_name':'EV simulation','language':'python'}))
    os.environ['JUPYTER_PATH']=str(temp)
    os.environ['JUPYTER_RUNTIME_DIR']=str(temp/'runtime')
    nb=nbformat.read(path,as_version=4)
    client=NotebookClient(nb,timeout=180,kernel_name='ev-sim',resources={'metadata':{'path':str(temp)}})
    executed=client.execute()
    outputs='\n'.join(o.get('text','') for c in executed.cells if c.cell_type=='code' for o in c.get('outputs',[]) if o.output_type=='stream')
    for expected in ['MATHEMATICAL_MODELS_VERIFIED','QISKIT_CIRCUITS_VERIFIED','BROWSER_VERIFIED','FAKE_DEVICE_SIMULATION_VERIFIED','EV_NOTEBOOK_VERIFIED']:
        assert expected in outputs,expected
    code_cells=[c for c in executed.cells if c.cell_type=='code']
    assert all(c.execution_count is not None for c in code_cells)
    assert not any(o.output_type=='error' for c in code_cells for o in c.outputs)
    # Remove temporary absolute paths from the notebook's writefile messages.
    for c in code_cells:
        for o in c.outputs:
            if o.output_type=='stream':
                import re
                o.text=re.sub(r'/[^\s]*ev-scheduling-notebook-[^\s]*/', 'temporary-source/',o.text)
    nbformat.write(executed,path)
    shutil.copy2(temp/'ev-scheduling-validation-results.json',ROOT/'ev-scheduling-validation-results.json')
    print(json.dumps({'cells':len(executed.cells),'code_cells_executed':len(code_cells),'errors':0}))
    print('EXECUTED_NOTEBOOK_VERIFIED')
