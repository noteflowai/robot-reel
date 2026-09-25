"""Freeze image inputs for a review of three previously published SmolVLA episodes."""
import hashlib
import json
from pathlib import Path


def main():
    import imageio_ffmpeg
    from PIL import Image, ImageDraw
    root = Path(__file__).resolve().parents[1]
    out = root / 'examples/model-review'
    out.mkdir(exist_ok=True)
    cases, source = [], []
    policy = '''Review a recorded robot episode using the supplied contact sheet. Return ONLY one JSON object with outcome ("success", "step_limit", or "unknown"), action_count (integer or null), cited_frames (an array of integer frame labels from this sheet), and explanation (at most 90 words). Explain observed behavior and uncertainty. Do not claim that images alone establish the simulator's success criterion or a causal failure mechanism. If a machine-readable record is supplied, distinguish its facts from your visual interpretation. Never invent a measurement.'''
    for label, condition in [('episode-a', 'reference'), ('episode-b', 'dim'), ('episode-c', 'camera')]:
        run = root / f'docs/stress/runs/seed-09-{condition}/attempt-001'
        trace = json.loads((run/'trace.json').read_text())
        indexes = [round(i*(len(trace['frames'])-1)/4) for i in range(5)]
        sheet = Image.new('RGB', (768, 5*280), '#0b1018')
        draw = ImageDraw.Draw(sheet)
        for camera, col in [('main',0), ('wrist',1)]:
            reader = imageio_ffmpeg.read_frames(str(run/f'{camera}.mp4'), pix_fmt='rgb24')
            meta = next(reader)
            for number, data in enumerate(reader):
                if number in indexes:
                    row = indexes.index(number)
                    im = Image.frombytes('RGB', meta['size'], data).resize((256,256))
                    sheet.paste(im,(col*384+64,row*280+24))
                    draw.text((col*384+8,row*280+6),f'{camera} | frame {number} | t={number/trace["fps"]:.2f}s',fill='white')
            reader.close()
        filename = f'{label}.png';sheet.save(out/filename)
        record = {'outcome':trace['result']['outcome'],'actions':trace['result']['actions'],'simulation_seconds':trace['result']['simulation_seconds'],'max_steps':trace['result']['max_steps'],'condition':condition,'physics_unchanged_by_condition':trace['stress']['physics_unchanged_by_condition']}
        source.append({'id':label,'condition':condition,'source_directory':run.relative_to(root).as_posix(),'source_commit':'f24849dd13860dd6c6989977647aeb2a1ecd6b2c','frame_indexes':indexes,'sheet':filename,'sheet_sha256':hashlib.sha256((out/filename).read_bytes()).hexdigest(),'files':{n:hashlib.sha256((run/n).read_bytes()).hexdigest() for n in ['trace.json','main.mp4','wrist.mp4']},'record':record})
        task = 'Task: '+trace['task']+'. Five sampled frames from each of two cameras are shown; frames between them are not supplied. '
        for mode in ['images-only','with-record']:
            prompt = task + ('No outcome record is supplied. Use unknown/null when not established.' if mode=='images-only' else 'Recorded facts: '+json.dumps(record)+'. These record fields are authoritative for the checks; explain what the images additionally suggest.')
            cases.append({'id':label+'-'+mode,'images':[filename],'prompt':prompt})
    protocol = {'schema':'robot-reel-model-review-protocol-1','frozen_on':'2026-09-25','policy':policy,'seeds':[17], 'generation':{'max_new_tokens':512,'temperature':0.6,'top_p':0.9,'top_k':20,'enable_thinking':False},'cases':cases,'scope':'One model generation per mode per episode; selected seed-09 episodes previously used by the public stress demo, not a representative benchmark. Images are decoded lossy video derivatives. No new policy rollout, intervention or physical success test. Explanations remain unverified interpretations.'}
    (out/'sources.json').write_text(json.dumps(source,indent=2)+'\n')
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')

if __name__ == '__main__':
    main()
