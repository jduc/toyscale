# Terraform basics: a playground

The "infrastructure" here is just **text files on your disk**. It's instant, free, and
harmless, but Terraform behaves exactly as it does with clusters or AWS VMs.

Concepts: [docs/01b-terraform-basics.md](../../docs/01b-terraform-basics.md).

Run everything from this folder:
```sh
cd playground/terraform-basics
```

---

### Step 1: `init`, which downloads the plugin
```sh
terraform init
ls -a                    # new: .terraform/ (the downloaded plugin) and .terraform.lock.hcl
```
👀 Terraform read `main.tf`, saw it needs `hashicorp/local`, and downloaded it.
You run `init` once per folder, and again whenever you add a provider.

### Step 2: `plan`, which shows what would happen
```sh
terraform plan
```
👀 It shows `+ create` for `local_file.greeting` and `Plan: 1 to add`.
**Nothing has been created yet.** Check: `ls output` → no such folder.

### Step 3: `apply`, which does it
```sh
terraform apply          # it shows the plan again, then asks; type: yes
cat output/hello.txt     # Hello, world!
terraform output         # greeting_file = "./output/hello.txt"
```

### Step 4: look at the state, Terraform's memory
```sh
cat terraform.tfstate    # just JSON! find "type": "local_file" and the "content"
terraform state list     # local_file.greeting
terraform state show local_file.greeting
```
👀 The state records "`local_file.greeting` = this real file". That's how Terraform knows what it owns.

### Step 5: apply again, which changes nothing
```sh
terraform apply
```
👀 `No changes. Your infrastructure matches the configuration.`
This is **declarative**: you describe the end result, not the actions. Running it 100 times is safe.

### Step 6: change an input
```sh
terraform plan  -var 'name=Julien'
terraform apply -var 'name=Julien'
cat output/hello.txt
```
👀 Look for `-/+ ... must be replaced` and `# forces replacement` next to `content`.
This provider can't edit a file in place, so it deletes and recreates it. This is the
same thing that happened when you renamed the cluster.

Now run `terraform plan` with no `-var`. It wants to go **back** to "world",
because the code says so. **The code is the truth, not the last command you typed.**
Run `terraform apply` to accept that.

### Step 7: drift, when reality changes behind Terraform's back
```sh
rm output/hello.txt
terraform plan           # → + create   (it noticed the file is gone)
terraform apply

echo "hacked" > output/hello.txt
terraform plan           # → it noticed the content differs, and will fix it
terraform apply
```
👀 `plan` always **refreshes** first: it checks the real world against the state,
then compares that with the code. Terraform only fixes drift when *you* run it.
It isn't a background process (Kubernetes is).

### Step 8: ✍️ your turn, write a second resource that depends on the first
Add this to `main.tf` yourself (type it, don't paste, to get a feel for the syntax):
```hcl
resource "local_file" "report" {
  filename = "${path.module}/output/report.txt"
  content  = "The greeting file is ${local_file.greeting.filename} and has ${length(local_file.greeting.content)} characters.\n"
}
```
```sh
terraform plan           # only "report" is new: 1 to add
terraform apply
cat output/report.txt
```
👀 `local_file.greeting.content` is a **reference** (TYPE.NAME.ATTRIBUTE). Because
`report` mentions `greeting`, Terraform knows greeting must exist first. You never
wrote any ordering. Then try:
```sh
terraform apply -var 'name=Ada'   # both files get replaced: report depends on greeting
```

### Step 9: ✍️ your turn again, add an output
Add an `output "report_file"` block that prints the report's filename, then `terraform apply`
and `terraform output`.

### Step 10: `destroy`
```sh
terraform destroy        # type yes
ls output                # empty: Terraform removed everything it created
terraform state list     # nothing: its memory is empty too
```