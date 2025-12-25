import pandas as pd
import datetime
import os
import json
import calendar
import locale

# Essayer de mettre en français pour les noms de mois, sinon fallback anglais
try:
    locale.setlocale(locale.LC_ALL, 'fr_FR.utf8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'fr_FR')
    except:
        pass

def analyze():
    print("Chargement des données globales...")
    
    # Structure de données finale : DATA[annee][mois] = { ... données ... }
    GLOBAL_DATA = {}

    # ---------------------------------------------------------
    # 1. CHARGEMENT FERIES
    # ---------------------------------------------------------
    feries_dates = set()
    warning_feries = ""
    feries_path = r"\\SRV-APP01\kpi\Suivi_Budget\Feries.xlsx"
    
    try:
        # Tentative directe de lecture (contourne les soucis potentiels de os.path.exists sur réseau)
        df_feries = pd.read_excel(feries_path)
        col_feries = df_feries.columns[0]
        # On stocke en string YYYY-MM-DD pour faciliter la sérialisation/comparaison
        feries_list = pd.to_datetime(df_feries[col_feries]).dt.date.tolist()
        feries_dates = set(feries_list)
        print(f"Jours fériés chargés: {len(feries_dates)}")

    except Exception as e:
        print(f"Erreur Feries ({feries_path}): {e}")
        warning_feries = f"⚠️ Attention : Erreur lors de la lecture du fichier Feries : {e}"

    # ---------------------------------------------------------
    # 2. CHARGEMENT BUDGET
    # ---------------------------------------------------------
    # Nouveau chemin réseau
    budget_path = r"\\SRV-APP01\kpi\Suivi_Budget\Budget.xlsx"
    df_budget = pd.DataFrame()
    warning_budget = ""

    try:
        # Tentative directe de lecture
        df_budget = pd.read_excel(budget_path, header=None, names=["MoisNum", "Annee", "MoisNom", "Budget"])
        print(f"Lignes Budget chargées: {len(df_budget)}")
    except Exception as e:
        print(f"Erreur Budget ({budget_path}): {e}")
        warning_budget = f"⚠️ Attention : Erreur lors de la lecture du fichier Budget : {e}"

    # ---------------------------------------------------------
    # 3. CHARGEMENT RESULTATS
    # ---------------------------------------------------------
    # Nouveau chemin et nom: resultats.xls
    # Colonnes : A=Date, B=Ignore, C=Cmd (cacdej), D=Exp (caexpj), E=Prod (caprodj)
    results_path = r"\\SRV-APP01\kpi\Suivi_Budget\resultat.xls"
    df_res = pd.DataFrame()
    warning_results = ""

    try:
        # On lit les 5 premières colonnes
        # On suppose qu'il y a une ligne d'en-tête, donc header=0. Si pas d'en-tête, mettre header=None.
        # Avec names=..., on renomme les colonnes lues.
        df_res = pd.read_excel(results_path, header=0, usecols="A:E", names=["datj", "ignore", "cacdej", "caexpj", "caprodj"])
        # On supprime la colonne inutile
        df_res.drop(columns=["ignore"], inplace=True)
        
        # Conversion dates
        df_res['datj'] = pd.to_datetime(df_res['datj'], errors='coerce')
        # Nettoyage
        df_res.dropna(subset=['datj'], inplace=True)
        
        print(f"Lignes Résultats chargées: {len(df_res)}")
        if not df_res.empty:
            print(f"Aperçu dates: du {df_res['datj'].min()} au {df_res['datj'].max()}")

    except Exception as e:
        print(f"Erreur Résultats ({results_path}): {e}")
        warning_results = f"⚠️ Attention : Erreur lors de la lecture du fichier Résultats : {e}"

    # Calcul date max (Mise à jour)
    last_update_str = "Inconnue"
    if not df_res.empty:
        max_date = df_res['datj'].max()
        last_update_str = max_date.strftime("%d/%m/%Y")
    
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # 4. CONSTRUCTION DE L'ARBRE DE DONNEES
    # ---------------------------------------------------------
    
    # Identification de toutes les années/mois uniques présents dans Budget OU Résultats
    # Set de tuples (annee, mois)
    all_periods = set()
    
    # Périodes du Budget
    if not df_budget.empty:
        for _, row in df_budget.iterrows():
            try:
                y = int(row['Annee'])
                m = int(row['MoisNum'])
                all_periods.add((y, m))
            except:
                pass
                
    # Périodes des Résultats
    if not df_res.empty:
        # Créer colonnes temp
        temp_years = df_res['datj'].dt.year
        temp_months = df_res['datj'].dt.month
        for y, m in zip(temp_years, temp_months):
            all_periods.add((y, m))
            
    sorted_periods = sorted(list(all_periods))
    print(f"Périodes identifiées (Année, Mois): {sorted_periods}")

    for year, month in sorted_periods:
        year_str = str(year)
        month_str = str(month)
        
        if year_str not in GLOBAL_DATA:
            GLOBAL_DATA[year_str] = {}
            
        # --- A. RECUPERATION BUDGET ---
        budget_val = 0
        if not df_budget.empty:
            # Filtre
            mask = (df_budget['Annee'] == year) & (df_budget['MoisNum'] == month)
            b_row = df_budget[mask]
            if not b_row.empty:
                budget_val = float(b_row.iloc[0]['Budget'])
        
        # --- B. TRAITEMENT RESULTATS QUOTIDIENS ---
        # Filtrer resultats pour ce mois/année
        start_date = pd.Timestamp(year, month, 1)
        # Dernier jour du mois
        last_day = calendar.monthrange(year, month)[1]
        end_date = pd.Timestamp(year, month, last_day)
        
        # Création de l'index complet des jours du mois
        full_date_range = pd.date_range(start=start_date, end=end_date, freq='D')
        
        # Filtrer DF
        monthly_res = pd.DataFrame()
        if not df_res.empty:
            mask_res = (df_res['datj'] >= start_date) & (df_res['datj'] <= end_date)
            monthly_res = df_res.loc[mask_res].copy()
        
        # Aggrégation par jour (au cas où doublons) et reindexation
        if not monthly_res.empty:
            daily_sums = monthly_res.groupby('datj')[['cacdej', 'caexpj', 'caprodj']].sum()
        else:
            daily_sums = pd.DataFrame(columns=['cacdej', 'caexpj', 'caprodj'])
            
        # Reindex pour avoir tous les jours (même sans prod) avec 0
        df_final = pd.DataFrame(index=full_date_range)
        df_final = df_final.join(daily_sums).fillna(0)
        
        # Calcul Cumul
        df_final['cumul_ca'] = df_final['cacdej'].cumsum()
        df_final['cumul_exp'] = df_final['caexpj'].cumsum()
        df_final['cumul_prod'] = df_final['caprodj'].cumsum()
        
        # Totaux Mensuels
        total_ca = float(df_final['cacdej'].sum())
        total_exp = float(df_final['caexpj'].sum())
        total_prod = float(df_final['caprodj'].sum())
        
        # --- C. JOURS OUVRES ET BUDGET CUMULÉ ---
        jours_ouvres = 0
        curr = start_date
        while curr <= end_date:
            # Samedi=5, Dimanche=6
            if curr.weekday() < 5 and curr.date() not in feries_dates:
                jours_ouvres += 1
            curr += datetime.timedelta(days=1)
            
        # Calcul du budget quotidien cible
        daily_budget_target = 0
        if jours_ouvres > 0:
            daily_budget_target = budget_val / jours_ouvres
            
        # Construction de la courbe de budget cumulé
        dataset_budget_cumul = []
        cumul_b = 0.0
        
        for d in df_final.index:
            # On vérifie si c'est un jour ouvré pour ajouter le budget
            is_working = d.weekday() < 5 and d.date() not in feries_dates
            if is_working:
                cumul_b += daily_budget_target
            dataset_budget_cumul.append(cumul_b)

        # --- D. PREPARATION JSON LEGER ---
        # On ne stocke que les listes pour les charts et les scalaires
        days_labels = [d.strftime('%d/%m') for d in df_final.index]
        dataset_ca = df_final['cumul_ca'].tolist()
        dataset_exp = df_final['cumul_exp'].tolist()
        dataset_prod = df_final['cumul_prod'].tolist()
        
        GLOBAL_DATA[year_str][month_str] = {
            "budget": budget_val,
            "realise": total_exp,      # SWAP: CA Réalisé = Expéditions
            "commandes": total_ca,     # SWAP: Prise de Commande = Commandes (ex-CA)
            "produit": total_prod,
            "jours_ouvres": jours_ouvres,
            "chart_labels": days_labels,
            "chart_ca": dataset_exp,   # SWAP: Chart principal = Expéditions
            "chart_cmd": dataset_ca,   # SWAP: Chart secondaire = Commandes
            "chart_prod": dataset_prod,
            "chart_budget_trend": dataset_budget_cumul
        }

    # --- E. AGREGATION ANNUELLE (A faire après avoir rempli tous les mois de l'année) ---
    for year_str in GLOBAL_DATA:
        months_data = GLOBAL_DATA[year_str]
        
        # On ne traite que s'il y a des mois, et on évite de retraiter si "0" existe déjà
        if not months_data or "0" in months_data:
            continue
            
        # Initialisation Annuels
        ann_budget = 0.0
        ann_realise = 0.0
        ann_commandes = 0.0
        ann_prod = 0.0
        ann_jours = 0
        
        # Pour les charts annuels : Histogramme Mensuel + Total
        chart_labels_y = []
        chart_budget_y = []
        chart_realise_y = []
        chart_cmd_y = []
        chart_prod_y = []
        
        # Liste des mois 1 à 12
        for m in range(1, 13):
            m_str = str(m)
            # Label
            chart_labels_y.append(f"{m:02d}") 
            
            val_b = 0.0
            val_r = 0.0
            val_c = 0.0
            val_p = 0.0

            if m_str in months_data:
                d = months_data[m_str]
                # Totaux Annuels
                ann_budget += d['budget']
                ann_realise += d['realise']
                ann_commandes += d['commandes']
                ann_prod += d['produit']
                ann_jours += d['jours_ouvres']
                
                # Valeurs Mensuelles (pour l'histogramme)
                val_b = d['budget']
                val_r = d['realise']
                val_c = d['commandes']
                val_p = d['produit']
            
            chart_budget_y.append(val_b)
            chart_realise_y.append(val_r)
            chart_cmd_y.append(val_c)
            chart_prod_y.append(val_p)

        # AJOUT DE LA COLONNE TOTAL
        chart_labels_y.append("TOTAL")
        chart_budget_y.append(ann_budget)
        chart_realise_y.append(ann_realise)
        chart_cmd_y.append(ann_commandes)
        chart_prod_y.append(ann_prod)

        GLOBAL_DATA[year_str]["0"] = {
            "budget": ann_budget,
            "realise": ann_realise,
            "commandes": ann_commandes,
            "produit": ann_prod,
            "jours_ouvres": ann_jours,
            "chart_labels": chart_labels_y,
            "chart_ca": chart_realise_y,
            "chart_cmd": chart_cmd_y,
            "chart_prod": chart_prod_y,
            "chart_budget_trend": chart_budget_y
        }

    # 5. GENERATION HTML/JS
    generate_spa(GLOBAL_DATA, last_update_str, warning_feries, warning_budget, warning_results, len(feries_dates), len(df_budget), len(df_res))


def generate_spa(data, last_update_str, warning_feries="", warning_budget="", warning_results="", nb_feries=0, nb_budget=0, nb_results=0):
    json_data = json.dumps(data)
    
    # Bloc Alerte HTML si warning
    alerts = []
    if warning_feries: alerts.append(warning_feries)
    if warning_budget: alerts.append(warning_budget)
    if warning_results: alerts.append(warning_results)
    
    alert_html = ""
    if alerts:
        # On affiche chaque alerte sur une ligne
        msgs_html = "<br>".join(alerts)
        alert_html = f'''
        <div style="background-color: #f39c12; color: white; text-align: center; padding: 10px; font-weight: bold;">
            {msgs_html}
        </div>
        '''
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dashboard Budgétaire Stratégique</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <!-- Google Fonts pour un look premium -->
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --primary: #2c3e50;
                --accent: #3498db;
                --success: #27ae60;
                --danger: #e74c3c;
                --exp: #9b59b6;
                --prod: #2ecc71;
                --bg: #f8f9fa;
                --card-bg: #ffffff;
                --text: #2c3e50;
                --text-light: #7f8c8d;
            }}
            
            body {{ font-family: 'Inter', sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 0; min-height: 100vh; }}
            
            /* --- LAYOUTS --- */
            .view {{ display: none; padding: 2rem; max-width: 1200px; margin: 0 auto; animation: fadein 0.3s; }}
            .view.active {{ display: block; }}
            
            @keyframes fadein {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}

            /* --- HOME VIEW (Year Selection) --- */
            .home-container {{ text-align: center; margin-top: 10vh; }}
            .home-title {{ font-size: 2.5rem; font-weight: 700; margin-bottom: 3rem; color: var(--primary); }}
            .year-grid {{ display: flex; justify-content: center; gap: 2rem; flex-wrap: wrap; }}
            .year-btn {{ 
                background: var(--card-bg); border: 2px solid var(--accent); color: var(--accent); 
                font-size: 2rem; padding: 2rem 4rem; border-radius: 12px; cursor: pointer; 
                transition: all 0.2s ease; box-shadow: 0 4px 6px rgba(0,0,0,0.05); font-weight: 600;
            }}
            .year-btn:hover {{ background: var(--accent); color: white; transform: translateY(-5px); box-shadow: 0 10px 15px rgba(52, 152, 219, 0.3); }}

            /* --- DASHBOARD VIEW --- */
            .top-bar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }}
            .back-btn {{ 
                background: none; border: none; color: var(--text-light); font-weight: 600; cursor: pointer; 
                display: flex; align-items: center; gap: 0.5rem; font-size: 1rem; padding: 0.5rem 1rem; border-radius: 6px;
            }}
            .back-btn:hover {{ background: rgba(0,0,0,0.05); color: var(--primary); }}
            
            .controls {{ display: flex; gap: 1rem; align-items: center; }}
            select {{ 
                padding: 0.8rem 1.5rem; border-radius: 8px; border: 1px solid #ddd; 
                font-size: 1rem; font-family: inherit; cursor: pointer; background-color: white; outline: none; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            }}

            .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }}
            .kpi-card {{ background: var(--card-bg); padding: 1.5rem; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); border-left: 5px solid transparent; }}
            .kpi-title {{ font-size: 0.85rem; text-transform: uppercase; color: var(--text-light); letter-spacing: 0.5px; margin-bottom: 0.5rem; }}
            .kpi-value {{ font-size: 1.8rem; font-weight: 700; color: var(--primary); }}
            .kpi-sub {{ font-size: 0.9rem; margin-top: 0.5rem; }}
            
            .row {{ display: grid; grid-template-columns: 1fr 2fr; gap: 2rem; margin-bottom: 2rem; }}
            @media (max-width: 900px) {{ .row {{ grid-template-columns: 1fr; }} }}
            
            .panel {{ background: var(--card-bg); padding: 2rem; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); }}
            .panel h2 {{ margin-top: 0; border-bottom: 1px solid #eee; padding-bottom: 1rem; font-size: 1.2rem; }}
            
            .metric-row {{ display: flex; justify-content: space-between; padding: 1rem 0; border-bottom: 1px solid #f0f0f0; }}
            .metric-row:last-child {{ border-bottom: none; }}
            .metric-val {{ font-family: 'Consolas', monospace; font-weight: 600; }}
            
            .chart-wrapper {{ position: relative; height: 400px; width: 100%; }}
            
            .positive {{ color: var(--success); }}
            .negative {{ color: var(--danger); }}
        </style>
    </head>
    <body>
        {alert_html}

        <!-- VIEW 1: HOME -->
        <div id="view-home" class="view active">
            <div class="home-container">
                <div class="home-title">Sélectionnez une Année</div>
                <div id="year-buttons" class="year-grid">
                    <!-- Généré par JS -->
                </div>
                
                <!-- BOUTON COMPARAISON -->
                <div style="margin-top: 3rem;">
                    <button onclick="goToComparison()" class="year-btn" style="font-size: 1.2rem; padding: 1rem 2rem; border-color: var(--exp); color: var(--exp);">
                        📊 Comparer les Années
                    </button>
                </div>

                <div style="margin-top: 3rem; color: var(--text-light); font-size: 0.9rem;">
                    Données mises à jour le : <strong>{last_update_str}</strong>
                    <span style="margin: 0 10px;">•</span>
                    Jours fériés chargés : <strong>{nb_feries}</strong>
                    <span style="margin: 0 10px;">•</span>
                    Lignes Budget chargées : <strong>{nb_budget}</strong>
                    <span style="margin: 0 10px;">•</span>
                    Lignes Résultats chargées : <strong>{nb_results}</strong>
                </div>
            </div>
        </div>

        <!-- VIEW 3: COMPARISON -->
        <div id="view-comparison" class="view">
            <div class="top-bar">
                <button class="back-btn" onclick="goHome()">← Retour à l'accueil</button>
                <div class="controls">
                    <h1 style="margin:0; font-size:1.5rem; color: var(--exp);">Comparaison Années</h1>
                </div>
            </div>
            
            <div class="panel">
                <div style="margin-bottom: 1rem;">
                    <strong>Afficher les années :</strong>
                    <div id="comp-toggles" style="display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 0.5rem;">
                        <!-- Checkboxes générées par JS -->
                    </div>
                </div>
                <div class="chart-wrapper" style="height: 500px;">
                    <canvas id="compChart"></canvas>
                </div>
            </div>
        </div>

        <!-- VIEW 2: DASHBOARD -->
        <div id="view-dashboard" class="view">
            <div class="top-bar">
                <button class="back-btn" onclick="goHome()">← Choisir une autre année</button>
                <div class="controls">
                    <h1 id="year-display" style="margin:0; font-size:1.5rem; margin-right:1rem;">2025</h1>
                    <select id="month-selector" onchange="selectMonth(this.value)">
                        <!-- Généré par JS -->
                    </select>
                </div>
            </div>

            <div class="kpi-grid">
                <div class="kpi-card" style="border-color: var(--accent);">
                    <div class="kpi-title">Jours Ouvrés</div>
                    <div class="kpi-value" id="kpi-days">-</div>
                </div>
                <div class="kpi-card" style="border-color: var(--primary);">
                    <div class="kpi-title">Objectif Budget</div>
                    <div class="kpi-value" id="kpi-budget">- €</div>
                </div>
                <div class="kpi-card" id="kpi-card-perf">
                    <div class="kpi-title">Réalisation</div>
                    <div class="kpi-value" id="kpi-percent">-%</div>
                </div>
            </div>

            <div class="row">
                <!-- COL GAUCHE: CHIFFRES -->
                <div class="panel">
                    <h2>Performance Mensuelle</h2>
                    <div class="metric-row">
                        <span>CA Réalisé</span>
                        <span class="metric-val" id="val-ca">-</span>
                    </div>
                    <div class="metric-row">
                        <span>Écart vs Budget</span>
                        <span class="metric-val" id="val-diff">-</span>
                    </div>
                    
                    <h2 style="margin-top:2rem;">Production & Commandes</h2>
                    <div class="metric-row">
                        <span>Prise de Commande</span>
                        <span class="metric-val" id="val-cmd">-</span>
                    </div>
                    <div class="metric-row">
                        <span>Montant Produit</span>
                        <span class="metric-val" id="val-prod">-</span>
                    </div>
                </div>

                <!-- COL DROITE: GRAPHIQUE -->
                <div class="panel">
                    <h2>Évolution Cumulée</h2>
                    <div class="chart-wrapper">
                        <canvas id="mainChart"></canvas>
                    </div>
                </div>
            </div>
            
        </div>

        <script>
            // DONNEES INJECTEES PAR PYTHON
            const DB_DATA = {json_data};
            
            // ETAT
            let currentYear = null;
            let currentMonth = null;
            let myChart = null;
            let compChart = null;

            // Noms de mois
            const MONTH_NAMES = {{
                "0": "Année Entière",
                "1": "Janvier", "2": "Février", "3": "Mars", "4": "Avril", "5": "Mai", "6": "Juin",
                "7": "Juillet", "8": "Août", "9": "Septembre", "10": "Octobre", "11": "Novembre", "12": "Décembre"
            }};

            function initHome() {{
                const container = document.getElementById('year-buttons');
                container.innerHTML = '';
                // Trier les années croissant
                const years = Object.keys(DB_DATA).sort((a,b) => a-b);
                years.forEach(y => {{
                    const btn = document.createElement('div');
                    btn.className = 'year-btn';
                    btn.innerText = y;
                    btn.onclick = () => selectYear(y);
                    container.appendChild(btn);
                }});
            }}

            function selectYear(year) {{
                currentYear = year;
                document.getElementById('view-home').classList.remove('active');
                document.getElementById('view-dashboard').classList.add('active');
                document.getElementById('year-display').innerText = year;
                
                // Peupler le selecteur de mois
                const monthSelect = document.getElementById('month-selector');
                monthSelect.innerHTML = '';
                
                // Sort months numerically, "0" will naturally come first
                const months = Object.keys(DB_DATA[year]).sort((a,b) => parseInt(a)-parseInt(b));
                months.forEach(m => {{
                    const opt = document.createElement('option');
                    opt.value = m;
                    opt.innerText = MONTH_NAMES[m] || m;
                    monthSelect.appendChild(opt);
                }});
                
                // Selectionner le premier par défaut (qui sera "0" -> Année Entière si présent, ou "1" Janvier)
                if (months.length > 0) {{
                    selectMonth(months[0]);
                }}
            }}

            function goHome() {{
                document.getElementById('view-dashboard').classList.remove('active');
                document.getElementById('view-comparison').classList.remove('active');
                document.getElementById('view-home').classList.add('active');
            }}

            // --- COMPARISON LOGIC ---
            function goToComparison() {{
                document.getElementById('view-home').classList.remove('active');
                document.getElementById('view-comparison').classList.add('active');
                initComparison();
            }}

            function initComparison() {{
                const years = Object.keys(DB_DATA).sort((a,b) => a-b);
                const container = document.getElementById('comp-toggles');
                container.innerHTML = '';
                
                years.forEach(y => {{
                    const label = document.createElement('label');
                    label.style = "display: flex; align-items: center; gap: 5px; cursor: pointer; user-select: none;";
                    
                    const cb = document.createElement('input');
                    cb.type = 'checkbox';
                    cb.value = y;
                    cb.checked = true; // par défaut tout coché
                    cb.onchange = updateCompChart;
                    
                    label.appendChild(cb);
                    label.appendChild(document.createTextNode(y));
                    container.appendChild(label);
                }});
                
                updateCompChart();
            }}

            function updateCompChart() {{
                // Récupérer les années cochées
                const checkboxes = document.querySelectorAll('#comp-toggles input[type="checkbox"]');
                const selectedYears = Array.from(checkboxes).filter(cb => cb.checked).map(cb => cb.value);
                
                const ctx = document.getElementById('compChart').getContext('2d');
                if (compChart) compChart.destroy();
                
                // Préparer datasets pour mois (Jan-Dec) et totaux annuels
                const colors = ['#3498db', '#e74c3c', '#9b59b6', '#2ecc71', '#f1c40f', '#34495e'];
                const datasets = [];
                
                selectedYears.forEach((y, idx) => {{
                    if (DB_DATA[y] && DB_DATA[y]["0"]) {{
                        const dataFull = DB_DATA[y]["0"].chart_ca; // CA Réalisé = Expéditions
                        const dataMonths = dataFull.slice(0, 12); // Jan-Dec
                        const dataTotal = dataFull[12]; // Total annuel
                        
                        // Dataset pour les mois (12 valeurs + null pour Total)
                        const monthData = [...dataMonths, null];
                        // Dataset pour le total (12 nulls + valeur totale)
                        const totalData = [...Array(12).fill(null), dataTotal];
                        
                        const color = colors[idx % colors.length];
                        
                        // Barres mensuelles (axe Y gauche)
                        datasets.push({{
                            label: "Chiffre d'affaires",
                            data: monthData,
                            backgroundColor: color,
                            borderColor: color,
                            borderWidth: 1,
                            yAxisID: 'y',
                            stack: 'stack' + idx
                        }});
                        
                        // Barre totale (axe Y droit)
                        datasets.push({{
                            label: y + ' (Total)',
                            data: totalData,
                            backgroundColor: color,
                            borderColor: color,
                            borderWidth: 1,
                            yAxisID: 'y1',
                            stack: 'total' + idx
                        }});
                    }}
                }});
                
                const labels = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc", "TOTAL"];
                
                compChart = new Chart(ctx, {{
                    type: 'bar',
                    data: {{
                        labels: labels,
                        datasets: datasets
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: {{ mode: 'index', intersect: false }},
                        plugins: {{
                            legend: {{ 
                                position: 'top',
                                labels: {{
                                    filter: function(item, chart) {{
                                        // Ne montrer que "Chiffre d'affaires" dans la légende
                                        return item.text === "Chiffre d'affaires";
                                    }}
                                }}
                            }},
                            tooltip: {{
                                callbacks: {{
                                    title: function(context) {{
                                        const label = context[0].label;
                                        return label;
                                    }},
                                    label: function(context) {{
                                        // Extraire l'année du label du dataset
                                        let yearLabel = context.dataset.label;
                                        if (yearLabel.includes('(Total)')) {{
                                            yearLabel = yearLabel.replace(' (Total)', '');
                                        }} else {{
                                            yearLabel = selectedYears[Math.floor(context.datasetIndex / 2)];
                                        }}
                                        
                                        let label = yearLabel + ': ';
                                        if (context.parsed.y !== null) {{
                                            label += new Intl.NumberFormat('fr-FR', {{ style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }}).format(context.parsed.y);
                                        }}
                                        return label;
                                    }}
                                }}
                            }}
                        }},
                        scales: {{
                            y: {{
                                beginAtZero: true,
                                position: 'left',
                                title: {{ display: true, text: 'Mensuel' }},
                                grid: {{ color: '#f0f0f0' }}
                            }},
                            y1: {{
                                beginAtZero: true,
                                position: 'right',
                                title: {{ display: true, text: 'Total Annuel' }},
                                grid: {{ drawOnChartArea: false }}
                            }}
                        }}
                    }}
                }});
            }}

            function selectMonth(m) {{
                currentMonth = m;
                document.getElementById('month-selector').value = m;
                updateDashboard();
            }}

            function updateDashboard() {{
                if (!currentYear || !currentMonth) return;
                
                const data = DB_DATA[currentYear][currentMonth];
                
                // 1. UPDATE KPIs
                document.getElementById('kpi-days').innerText = data.jours_ouvres;
                document.getElementById('kpi-budget').innerText = formatMoney(data.budget);
                
                const percent = data.budget > 0 ? (data.realise / data.budget * 100) : 0;
                const kpiPercent = document.getElementById('kpi-percent');
                kpiPercent.innerText = percent.toFixed(1) + '%';
                
                // Couleur dynamique KPI
                const kpiCard = document.getElementById('kpi-card-perf');
                const isGood = percent >= 100;
                kpiCard.style.borderColor = isGood ? 'var(--success)' : 'var(--danger)';
                kpiPercent.className = 'kpi-value ' + (isGood ? 'positive' : 'negative');

                // 2. UPDATE TABLE
                document.getElementById('val-ca').innerText = formatMoney(data.realise);
                document.getElementById('val-cmd').innerText = formatMoney(data.commandes);
                document.getElementById('val-prod').innerText = formatMoney(data.produit);
                
                const diff = data.realise - data.budget;
                const elDiff = document.getElementById('val-diff');
                elDiff.innerText = (diff > 0 ? '+' : '') + formatMoney(diff);
                elDiff.className = 'metric-val ' + (diff >= 0 ? 'positive' : 'negative');

                // 3. UPDATE CHART
                updateChart(data);
            }}

            function formatMoney(amount) {{
                return new Intl.NumberFormat('fr-FR', {{ style: 'currency', currency: 'EUR' }}).format(amount);
            }}

            function updateChart(data) {{
                const ctx = document.getElementById('mainChart').getContext('2d');
                
                if (myChart) {{
                    myChart.destroy();
                }}

                // Détection Type de Graph
                // Si "0" (Année entière) => Bar chart (Histogramme)
                // Sinon => Line chart (Courbe cumulée)
                const isYearView = (currentMonth === "0");
                const chartType = isYearView ? 'bar' : 'line';
                const tensionVal = isYearView ? 0 : 0.4;
                const fillVal = isYearView ? false : true;
                
                // Adaptation visuelle Budget
                const budgetType = isYearView ? 'bar' : 'line'; // On peut mixer
                const budgetLabel = isYearView ? 'Budget Mensuel' : 'Budget Cible (Trend)';
                const budgetBorderDash = isYearView ? [] : [2, 2];
                // Afficher le budget en ligne rouge même sur l'histo pour bien voir ?
                // Ou en barre rouge ? Le prompt dit "Histogramme mensuel", donc tout barres c'est plus sûr.
                
                // Configuration des Axes (Scales)
                const scalesConfig = {{
                    y: {{
                        beginAtZero: true,
                        position: 'left',
                        grid: {{ color: '#f0f0f0' }},
                        title: {{ display: isYearView, text: 'Mensuel' }}
                    }},
                    x: {{ grid: {{ display: false }} }}
                }};

                // Si vue annuelle : Axe Y1 à droite pour le Total
                if (isYearView) {{
                    scalesConfig.y1 = {{
                        beginAtZero: true,
                        position: 'right',
                        grid: {{ drawOnChartArea: false }}, // avoid grid clutter
                        title: {{ display: true, text: 'Cumul Annuel (Total)' }}
                    }};
                }}

                // Construction des Datasets
                let finalDatasets = [];

                if (isYearView) {{
                    // Fonctions pour séparer Mois (0-11) et Total (12)
                    // On suppose data.chart_labels a 13 entrées (01..12, TOTAL)
                    const splitData = (arr) => {{
                        const monthly = arr.slice(0, 12);
                        const dMonth = [...monthly, null];
                        const dTotal = [...Array(12).fill(null), arr[12]];
                        return {{ dMonth, dTotal }};
                    }};

                    const b = splitData(data.chart_budget_trend);
                    const r = splitData(data.chart_ca);
                    const c = splitData(data.chart_cmd);
                    const p = splitData(data.chart_prod);
                    
                    finalDatasets = [
                        // PAIRES : On met le même label pour que la légende soit propre (ou concaténé)
                        // BUDGET
                        {{
                            label: 'Budget',
                            data: b.dMonth,
                            borderColor: '#e74c3c',
                            backgroundColor: '#e74c3c',
                            type: 'line', 
                            borderWidth: 2,
                            pointRadius: 3,
                            tension: 0.1,
                            yAxisID: 'y'
                        }},
                        {{
                            label: 'Budget (Total)',
                            data: b.dTotal,
                            borderColor: '#e74c3c',
                            backgroundColor: '#e74c3c',
                            type: 'bar', // Total en barre aussi ou point ? Barre c'est mieux si tout est barre
                            borderWidth: 2,
                            yAxisID: 'y1'
                        }},
                        // CA
                        {{
                            label: 'CA Réalisé',
                            data: r.dMonth,
                            backgroundColor: '#3498db',
                            borderColor: '#3498db',
                            borderWidth: 1,
                            yAxisID: 'y'
                        }},
                        {{
                            label: 'CA (Total)',
                            data: r.dTotal,
                            backgroundColor: '#3498db', // Plus sombre ?
                            borderColor: '#3498db',
                            borderWidth: 1,
                            yAxisID: 'y1'
                        }},
                        // CMD
                        {{
                            label: 'Prise de Cde',
                            data: c.dMonth,
                            backgroundColor: '#9b59b6',
                            borderColor: '#9b59b6',
                            borderWidth: 1,
                            yAxisID: 'y'
                        }},
                        {{
                            label: 'Cde (Total)',
                            data: c.dTotal,
                            backgroundColor: '#9b59b6',
                            borderColor: '#9b59b6',
                            borderWidth: 1,
                            yAxisID: 'y1'
                        }},
                        // PROD
                        {{
                            label: 'Produit',
                            data: p.dMonth,
                            backgroundColor: '#2ecc71',
                            borderColor: '#2ecc71',
                            borderWidth: 1,
                            yAxisID: 'y'
                        }},
                        {{
                            label: 'Prod (Total)',
                            data: p.dTotal,
                            backgroundColor: '#2ecc71',
                            borderColor: '#2ecc71',
                            borderWidth: 1,
                            yAxisID: 'y1'
                        }}
                    ];

                }} else {{
                    // Vue Mensuelle Normale
                    finalDatasets = [
                        {{
                            label: budgetLabel,
                            data: data.chart_budget_trend,
                            borderColor: '#e74c3c',
                            backgroundColor: 'transparent',
                            type: 'line',
                            borderWidth: 2,
                            borderDash: budgetBorderDash,
                            pointRadius: 0,
                            tension: 0.1,
                            yAxisID: 'y'
                        }},
                        {{
                            label: 'CA Réalisé',
                            data: data.chart_ca,
                            borderColor: '#3498db',
                            backgroundColor: 'rgba(52, 152, 219, 0.1)',
                            borderWidth: 3,
                            fill: fillVal,
                            tension: tensionVal,
                             yAxisID: 'y'
                        }},
                         {{
                            label: 'Prise de Cde',
                            data: data.chart_cmd,
                            borderColor: '#9b59b6',
                            backgroundColor: 'transparent',
                            borderWidth: 2,
                            borderDash: [5, 5],
                            tension: tensionVal,
                             yAxisID: 'y'
                        }},
                         {{
                            label: 'Produit',
                            data: data.chart_prod,
                            borderColor: '#2ecc71',
                            backgroundColor: 'transparent',
                            borderWidth: 2,
                            tension: tensionVal,
                             yAxisID: 'y'
                        }}
                    ];
                }}
                
                myChart = new Chart(ctx, {{
                    type: chartType,
                    data: {{
                        labels: data.chart_labels, // [01..12, TOTAL]
                        datasets: finalDatasets
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: {{ mode: 'index', intersect: false }},
                        plugins: {{
                            legend: {{ position: 'bottom' }},
                            tooltip: {{
                                callbacks: {{
                                    label: function(context) {{
                                        let label = context.dataset.label || '';
                                        if (label) label += ': ';
                                        if (context.parsed.y !== null) {{
                                            label += new Intl.NumberFormat('fr-FR', {{ style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }}).format(context.parsed.y);
                                        }}
                                        return label;
                                    }}
                                }}
                            }}
                        }},
                        scales: scalesConfig
                    }}
                }});
            }}

            // Start
            initHome();
        </script>
    </body>
    </html>
    """
    
    with open("dashboard_dynamique.html", "w", encoding='utf-8') as f:
        f.write(html_content)
    print("Fichier généré: dashboard_dynamique.html")

if __name__ == "__main__":
    analyze()
