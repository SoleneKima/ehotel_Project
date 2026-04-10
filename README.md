# 🏨 e-Hotel Management System

## 📌 Description

e-Hotel est une application web développée avec Flask permettant la gestion complète d’un système hôtelier.
Elle permet aux gestionnaires de gérer les hôtels, chambres, employés et locations, et aux clients de rechercher et réserver des chambres.

---

## ⚙️ Technologies utilisées

* **Backend** : Python (Flask)
* **Frontend** : HTML, CSS
* **Base de données** : PostgreSQL
* **Outils** : pgAdmin, GitHub

---

##  Fonctionnalités principales

### 👤 Authentification

* Connexion en tant que :

  * Gestionnaire
  * Client

### 🏨 Gestion des données

* Clients
* Employés
* Hôtels
* Chambres

### 🔎 Recherche avancée

* Dates
* Capacité
* Superficie
* Chaîne hôtelière
* Catégorie
* Nombre de chambres
* Prix

### 📅 Réservations & Locations

* Réserver une chambre
* Louer une chambre
* Conversion réservation → location

---

## 🔐 Gestion des rôles

* **Gestionnaire** :

  * Accès complet (CRUD)
* **Client** :

  * Recherche + réservation uniquement

---

## 🗄️ Base de données

Le fichier `ehotel.sql` contient :

* La structure complète
* Les données nécessaires au fonctionnement

---

## ▶️ Lancer le projet

1. Cloner le dépôt :

```bash
git clone <repo_url>
```

2. Installer les dépendances :

```bash
pip install -r requirements.txt
```

3. Lancer l’application :

```bash
python app.py
```

4. Accéder :

```
http://127.0.0.1:5000
```

---

## 👨‍💻 Auteur

Projet réalisé dans le cadre d’un cours.
