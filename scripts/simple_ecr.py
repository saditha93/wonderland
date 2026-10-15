"""Publish local Docker archives using bounded, checksum-verified ECR parts."""
import gzip
import hashlib
import json
import tarfile
import httpx

from scripts.cloud import GuardError


def publish(client, archive, repository, tag, expected_image, architecture,
            registry=None, auth=None, mount_source=None):
    with tarfile.open(archive) as source:
        entries = json.load(source.extractfile('manifest.json'))
        if len(entries) != 1 or entries[0]['RepoTags'] != [expected_image]:
            raise GuardError('Docker archive does not contain the expected single image')
        entry = entries[0]
        config = source.extractfile(entry['Config']).read()
        metadata = json.loads(config)
        if metadata.get('architecture') != architecture or metadata.get('os') != 'linux':
            raise GuardError('Docker archive architecture differs from the server')

        def upload(data):
            digest = 'sha256:' + hashlib.sha256(data).hexdigest()
            available = client.batch_check_layer_availability(
                repositoryName=repository, layerDigests=[digest])
            if any(x.get('layerAvailability') == 'AVAILABLE' for x in available['layers']):
                return digest
            if registry and auth and mount_source and repository != mount_source:
                response = httpx.post(registry+'/v2/'+repository+'/blobs/uploads/',
                    params={'mount':digest,'from':mount_source},auth=auth,
                    timeout=45,follow_redirects=False)
                if response.status_code == 201:
                    print('Reused shared ECR layer:', repository, digest, flush=True)
                    return digest
                if response.status_code != 202:
                    raise GuardError('ECR shared-layer request refused: '+str(response.status_code))
            initiated = client.initiate_layer_upload(repositoryName=repository)
            part_size = min(initiated['partSize'], 5 * 1024 * 1024)
            if not 5 * 1024 * 1024 <= part_size <= 20 * 1024 * 1024:
                raise GuardError('Unexpected ECR upload part size')
            for offset in range(0, len(data), part_size):
                part = data[offset:offset + part_size]
                client.upload_layer_part(repositoryName=repository,
                    uploadId=initiated['uploadId'], partFirstByte=offset,
                    partLastByte=offset + len(part) - 1, layerPartBlob=part)
                print('ECR upload:', repository, offset + len(part), '/', len(data), flush=True)
            completed = client.complete_layer_upload(repositoryName=repository,
                uploadId=initiated['uploadId'], layerDigests=[digest])
            if completed['layerDigest'] != digest:
                raise GuardError('ECR completed layer digest differs')
            return digest

        config_descriptor = {'mediaType':'application/vnd.docker.container.image.v1+json',
                             'digest':upload(config), 'size':len(config)}
        layers = []
        for path in entry['Layers']:
            data = source.extractfile(path).read()
            if path.startswith('blobs/sha256/') and hashlib.sha256(data).hexdigest() != path.rsplit('/', 1)[1]:
                raise GuardError('Local Docker archive blob checksum differs')
            if not data.startswith(b'\x1f\x8b'):
                data = gzip.compress(data, mtime=0)
            layers.append({'mediaType':'application/vnd.docker.image.rootfs.diff.tar.gzip',
                           'digest':upload(data), 'size':len(data)})
        manifest = json.dumps({'schemaVersion':2,
            'mediaType':'application/vnd.docker.distribution.manifest.v2+json',
            'config':config_descriptor, 'layers':layers}, separators=(',', ':'))
        result = client.put_image(repositoryName=repository, imageTag=tag,
                                  imageManifest=manifest)
        print('Published immutable image:', repository, result['image']['imageId']['imageDigest'], flush=True)
