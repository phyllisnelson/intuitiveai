package provider

import (
	"fmt"
	"net/http"
	"os"
	"testing"
	"time"

	"github.com/hashicorp/terraform-plugin-go/tfprotov6"
	"github.com/hashicorp/terraform-plugin-framework/providerserver"
	"github.com/hashicorp/terraform-plugin-testing/helper/resource"
)

func testAccProviderConfig() (string, string, string) {
	baseURL := os.Getenv("TF_ACC_VMAPI_BASE_URL")
	if baseURL == "" {
		baseURL = "http://localhost:8000"
	}

	apiKey := os.Getenv("TF_ACC_VMAPI_API_KEY")
	if apiKey == "" {
		apiKey = "changeme"
	}

	providerConfig := fmt.Sprintf(`
provider "vmapi" {
  base_url              = %q
  api_key               = %q
  poll_interval_seconds = 2
  poll_timeout_seconds  = 60
}
`, baseURL, apiKey)

	return providerConfig, baseURL, apiKey
}

func testAccPreCheck(t *testing.T, baseURL, apiKey string) {
	t.Helper()

	req, err := http.NewRequest(http.MethodGet, baseURL+"/health", nil)
	if err != nil {
		t.Fatalf("failed to build health request: %v", err)
	}
	req.Header.Set("X-API-Key", apiKey)

	resp, err := (&http.Client{Timeout: 5 * time.Second}).Do(req)
	if err != nil {
		t.Fatalf("failed reaching API at %s: %v", baseURL, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("API health check returned %d (expected 200)", resp.StatusCode)
	}
}

func TestAccDataSources_FlavorsAndImages(t *testing.T) {
	providerConfig, baseURL, apiKey := testAccProviderConfig()

	resource.Test(t, resource.TestCase{
		PreCheck: func() {
			testAccPreCheck(t, baseURL, apiKey)
		},
		ProtoV6ProviderFactories: map[string]func() (tfprotov6.ProviderServer, error){
			"vmapi": providerserver.NewProtocol6WithError(New("test")()),
		},
		Steps: []resource.TestStep{
			{
				Config: providerConfig + `

data "vmapi_flavors" "all" {
  limit  = 20
  offset = 0
}

data "vmapi_images" "all" {
  limit  = 20
  offset = 0
}
`,
				Check: resource.ComposeTestCheckFunc(
					resource.TestCheckResourceAttrSet("data.vmapi_flavors.all", "total"),
					resource.TestCheckResourceAttrSet("data.vmapi_images.all", "total"),
				),
			},
		},
	})
}

func TestAccResourceVM_Basic(t *testing.T) {
	providerConfig, baseURL, apiKey := testAccProviderConfig()
	name := fmt.Sprintf("tf-acc-vm-%d", time.Now().UnixNano())

	resource.Test(t, resource.TestCase{
		PreCheck: func() {
			testAccPreCheck(t, baseURL, apiKey)
		},
		ProtoV6ProviderFactories: map[string]func() (tfprotov6.ProviderServer, error){
			"vmapi": providerserver.NewProtocol6WithError(New("test")()),
		},
		Steps: []resource.TestStep{
			{
				Config: providerConfig + fmt.Sprintf(`

data "vmapi_flavors" "all" {
  limit = 20
}

data "vmapi_images" "all" {
  limit = 20
}

resource "vmapi_vm" "test" {
  name      = %q
  flavor_id = data.vmapi_flavors.all.flavors[0].id
  image_id  = data.vmapi_images.all.images[0].id

  metadata = {
    managed_by = "terraform-acc"
  }
}
`, name),
				Check: resource.ComposeTestCheckFunc(
					resource.TestCheckResourceAttr("vmapi_vm.test", "name", name),
					resource.TestCheckResourceAttrSet("vmapi_vm.test", "id"),
					resource.TestCheckResourceAttrSet("vmapi_vm.test", "status"),
				),
			},
		},
	})
}

func TestAccResourceVolume_CreateAndResize(t *testing.T) {
	providerConfig, baseURL, apiKey := testAccProviderConfig()
	name := fmt.Sprintf("tf-acc-volume-%d", time.Now().UnixNano())

	resource.Test(t, resource.TestCase{
		PreCheck: func() {
			testAccPreCheck(t, baseURL, apiKey)
		},
		ProtoV6ProviderFactories: map[string]func() (tfprotov6.ProviderServer, error){
			"vmapi": providerserver.NewProtocol6WithError(New("test")()),
		},
		Steps: []resource.TestStep{
			{
				Config: providerConfig + fmt.Sprintf(`
resource "vmapi_volume" "test" {
  name    = %q
  size_gb = 5
}
`, name),
				Check: resource.ComposeTestCheckFunc(
					resource.TestCheckResourceAttr("vmapi_volume.test", "name", name),
					resource.TestCheckResourceAttr("vmapi_volume.test", "size_gb", "5"),
					resource.TestCheckResourceAttrSet("vmapi_volume.test", "id"),
				),
			},
			{
				Config: providerConfig + fmt.Sprintf(`
resource "vmapi_volume" "test" {
  name    = %q
  size_gb = 6
}
`, name),
				Check: resource.TestCheckResourceAttr("vmapi_volume.test", "size_gb", "6"),
			},
		},
	})
}
