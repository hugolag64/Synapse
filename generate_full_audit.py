import os

def generate_tree(startpath, exclude_dirs):
    tree_str = "ARBORESCENCE DU PROJET :\n========================\n"
    for root, dirs, files in os.walk(startpath):
        # Filtrage des dossiers
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in exclude_dirs]
        
        # Ignorer si on détecte un environnement virtuel par son contenu
        if 'pyvenv.cfg' in files or ('Lib' in dirs and 'site-packages' in os.listdir(os.path.join(root, 'Lib')) if 'Lib' in dirs else False):
            dirs[:] = []
            continue

        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        tree_str += f"{indent}{os.path.basename(root)}/\n"
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            if not f.startswith('.'):
                tree_str += f"{subindent}{f}\n"
    return tree_str + "\n\n"

def create_full_audit_text():
    project_root = os.path.dirname(os.path.abspath(__file__))
    output_filename = "audit_complet_gemini.txt"
    output_path = os.path.join(project_root, output_filename)
    
    # Dossiers standard à ignorer (dépendances, environnements, caches)
    exclude_dirs = {
        '.venv', 'venv', 'env', 'virtualenv', '__pycache__', '.git', 
        'storage_index', 'storage_chroma', 'temp_uploads', 
        'synapse_edn_test', 'static', 'node_modules', '.idea', 
        '.vscode', 'dist', 'build', 'logs', 'data', '.pytest_cache', '.claude'
    }
    
    # Fichiers spécifiques à ignorer (secrets, caches, résultats d'audit, etc.)
    exclude_files = {
        output_filename.lower(), 
        'token.json',
        'credentials.json',
        'data_cache.json',
        '.env',
        'pdf_status.txt'
    }

    print(f"Génération du fichier d'audit global : {output_filename}...")
    
    with open(output_path, 'w', encoding='utf-8') as outfile:
        # Ajout de l'arborescence en début de fichier
        tree = generate_tree(project_root, exclude_dirs)
        outfile.write(tree)
        
        for root, dirs, files in os.walk(project_root):
            # Filtrer dynamiquement les dossiers
            valid_dirs = []
            for d in dirs:
                if d.startswith('.'):
                    continue
                if d in exclude_dirs:
                    continue
                
                # Détecter et ignorer les environnements virtuels
                full_dir_path = os.path.join(root, d)
                if os.path.exists(os.path.join(full_dir_path, 'pyvenv.cfg')):
                    continue
                if os.path.exists(os.path.join(full_dir_path, 'Lib', 'site-packages')):
                    continue
                
                valid_dirs.append(d)
            dirs[:] = valid_dirs
            
            for file in files:
                # Normalisation du nom de fichier
                file_lower = file.lower()
                
                # Extensions de fichiers autorisées (élargies pour capter tout le code brut)
                allowed_extensions = (
                    '.py', '.html', '.css', '.js', '.jsx', '.ts', '.tsx', 
                    '.json', '.txt', '.bat', '.sh', '.env.example', 
                    '.md', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.vue',
                    '.sql'
                )
                
                if (file_lower.endswith(allowed_extensions) or file_lower == '.env.example') and file_lower not in exclude_files and not file_lower.startswith('.'):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, project_root)
                    
                    # Ignorer les fichiers volumineux non-code (ex: caches JSON ou gros TXT) pour éviter de saturer l'audit
                    if file_lower.endswith(('.txt', '.json')):
                        try:
                            if os.path.getsize(file_path) > 50000: # 50 KB limit
                                print(f"Ignoré (trop volumineux) : {rel_path}")
                                continue
                        except OSError:
                            pass
                    
                    # En-tête pour bien délimiter les fichiers pour l'IA
                    outfile.write(f"\n\n{'='*60}\n")
                    outfile.write(f"CHEMIN DU FICHIER : {rel_path}\n")
                    outfile.write(f"{'='*60}\n\n")
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as infile:
                            outfile.write(infile.read())
                        print(f"Ajout : {rel_path}")
                    except Exception as e:
                        outfile.write(f"Erreur de lecture du fichier : {e}\n")
                        print(f"Erreur sur {rel_path} : {e}")
                        
    print(f"\nTerminé ! L'ensemble de votre code brut est regroupé dans : {output_path}")

if __name__ == "__main__":
    create_full_audit_text()
